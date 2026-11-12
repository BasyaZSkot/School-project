"""OAuth 2.0 authorization-code flows for Google and Yandex ID."""

from __future__ import annotations

from hashlib import sha256
import base64
import os
from urllib.parse import urlencode

import httpx


PROVIDERS = {
    "google": {
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
        "redirect_uri_env": "GOOGLE_REDIRECT_URI",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "profile_url": "https://openidconnect.googleapis.com/v1/userinfo",
    },
    "yandex": {
        "client_id_env": "YANDEX_CLIENT_ID",
        "client_secret_env": "YANDEX_CLIENT_SECRET",
        "redirect_uri_env": "YANDEX_REDIRECT_URI",
        "authorize_url": "https://oauth.yandex.ru/authorize",
        "token_url": "https://oauth.yandex.ru/token",
        "profile_url": "https://login.yandex.ru/info?format=json",
    },
}


def settings(provider: str) -> dict[str, str] | None:
    spec = PROVIDERS.get(provider)
    if not spec:
        return None
    values = {
        "client_id": os.getenv(spec["client_id_env"], "").strip(),
        "client_secret": os.getenv(spec["client_secret_env"], "").strip(),
        "redirect_uri": os.getenv(spec["redirect_uri_env"], "").strip(),
    }
    return values if all(values.values()) else None


def configured_providers() -> dict[str, bool]:
    return {name: settings(name) is not None for name in PROVIDERS}


def pkce_challenge(verifier: str) -> str:
    digest = sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorization_url(provider: str, state: str, verifier: str) -> str:
    config = settings(provider)
    if not config:
        raise ValueError(f"{provider} OAuth is not configured")
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "state": state,
        "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if provider == "google":
        params["scope"] = "openid email profile"
    else:
        params["scope"] = "login:info login:email"
    return PROVIDERS[provider]["authorize_url"] + "?" + urlencode(params)


async def fetch_profile(provider: str, code: str, verifier: str) -> dict[str, str | bool | None]:
    config = settings(provider)
    if not config:
        raise ValueError(f"{provider} OAuth is not configured")

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": config["redirect_uri"],
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        token_response = await client.post(PROVIDERS[provider]["token_url"], data=token_data)
        token_response.raise_for_status()
        token_payload = token_response.json()
        access_token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
        if not access_token:
            raise ValueError("OAuth provider did not return an access token")

        auth_scheme = "Bearer" if provider == "google" else "OAuth"
        profile_response = await client.get(
            PROVIDERS[provider]["profile_url"],
            headers={"Authorization": f"{auth_scheme} {access_token}"},
        )
        profile_response.raise_for_status()
        profile = profile_response.json()

    if not isinstance(profile, dict):
        raise ValueError("OAuth provider returned an invalid profile")
    if provider == "google":
        if not profile.get("email_verified"):
            raise ValueError("Google account email is not verified")
        subject = profile.get("sub")
        email = profile.get("email")
        name = profile.get("name") or email
        picture_url = profile.get("picture")
    else:
        subject = profile.get("id") or profile.get("psuid")
        email = profile.get("default_email")
        name = profile.get("real_name") or profile.get("display_name") or profile.get("login") or email
        picture_url = None

    if not subject:
        raise ValueError("OAuth provider did not return a stable account ID")
    return {
        "subject": str(subject),
        "email": str(email) if email else None,
        "name": str(name) if name else "Пользователь",
        "picture_url": str(picture_url) if picture_url else None,
        "email_verified": provider=="google" and profile.get("email_verified") is True,
    }

