"""Resilient HTTP transport for public marketplace pages.

Reduces avoidable blocks and survives temporary ones:

* current browser-like header profile, kept consistent per host;
* per-host rate limiting with jitter and a short response cache;
* retries with exponential backoff, honouring ``Retry-After``;
* session cookies issued by the site itself, reused between requests;
* optional proxies supplied by the operator (``MULTIMARKET_PROXY_URLS``),
  rotated round-robin and put on cooldown after failures;
* detection of challenge/CAPTCHA pages that arrive with HTTP 200.

It does not solve CAPTCHAs, log in or call private APIs. When a site keeps
refusing, ``httpx.HTTPStatusError`` or ``BlockedError`` is raised and the
service reports ``policy_restricted`` with a link to the site's own search.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("multimarket.transport")

# Keep in sync with the current stable Chrome (checked November 2026).
# A stale version is itself a common bot signal; override with
# MULTIMARKET_USER_AGENT if you need something specific.
CHROME_MAJOR = 156

BLOCK_STATUSES = frozenset({401, 403, 429, 498})
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER = 30.0

# Real search/product pages are far larger than challenge pages, so markers
# are only checked in small responses to avoid false positives.
CHALLENGE_MAX_CHARS = 20_000
CHALLENGE_MARKERS = (
    "captcha",
    "showcaptcha",
    "access denied",
    "доступ ограничен",
    "подтвердите, что вы не робот",
    "проверка безопасности",
    "are you a robot",
)

_ACCEPT_HTML = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)


class BlockedError(Exception):
    """The site answered with a challenge/CAPTCHA page instead of content."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _chrome_headers(platform: str, platform_hint: str) -> dict[str, str]:
    major = CHROME_MAJOR
    return {
        "User-Agent": (
            f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.0.0 Safari/537.36"
        ),
        "Accept": _ACCEPT_HTML,
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": (
            f'"Chromium";v="{major}", "Google Chrome";v="{major}", '
            '"Not_A Brand";v="24"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{platform_hint}"',
    }


def browser_profiles() -> list[dict[str, str]]:
    return [
        _chrome_headers("Windows NT 10.0; Win64; x64", "Windows"),
        _chrome_headers("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
    ]


def _env_number(name: str, default: float, minimum: float, cast=float):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def parse_proxy_urls(raw: str) -> tuple[str, ...]:
    proxies: list[str] = []
    for item in raw.replace("\n", ",").split(","):
        item = item.strip()
        if not item:
            continue
        parsed = urlparse(item)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            # Never echo the value: proxy URLs usually contain credentials.
            raise ValueError(
                "MULTIMARKET_PROXY_URLS must be a comma-separated list of "
                "http(s)://[user:pass@]host:port URLs"
            )
        proxies.append(item)
    return tuple(dict.fromkeys(proxies))


@dataclass(slots=True)
class FetcherConfig:
    max_attempts: int = 3
    min_interval: float = 1.0
    jitter: float = 0.5
    backoff_base: float = 1.0
    cache_ttl: float = 60.0
    timeout: float = 10.0
    total_timeout: float = 20.0
    proxies: tuple[str, ...] = ()
    proxy_cooldown: float = 300.0
    user_agent: str | None = None
    impersonate: str | None = None

    @classmethod
    def from_env(cls) -> "FetcherConfig":
        return cls(
            max_attempts=_env_number("MULTIMARKET_FETCH_ATTEMPTS", 3, 1, int),
            min_interval=_env_number("MULTIMARKET_MIN_REQUEST_INTERVAL", 1.0, 0.0),
            cache_ttl=_env_number("MULTIMARKET_CACHE_TTL", 60.0, 0.0),
            total_timeout=_env_number("MULTIMARKET_FETCH_TOTAL_TIMEOUT", 20.0, 1.0),
            proxies=parse_proxy_urls(os.getenv("MULTIMARKET_PROXY_URLS", "")),
            proxy_cooldown=_env_number("MULTIMARKET_PROXY_COOLDOWN", 300.0, 0.0),
            user_agent=os.getenv("MULTIMARKET_USER_AGENT", "").strip() or None,
            impersonate=os.getenv("MULTIMARKET_IMPERSONATE", "").strip() or None,
        )


@dataclass(slots=True)
class FetchedPage:
    url: str
    text: str
    status_code: int


class ProxyPool:
    """Round-robin proxies; a failing proxy rests for ``cooldown`` seconds."""

    def __init__(self, proxies=(), cooldown: float = 300.0, clock=time.monotonic):
        self._proxies = list(dict.fromkeys(proxies))
        self._cooldown = cooldown
        self._clock = clock
        self._banned_until: dict[str, float] = {}
        self._cursor = 0

    def __len__(self) -> int:
        return len(self._proxies)

    def acquire(self) -> str | None:
        """Next healthy proxy, or ``None`` when no proxies are configured."""
        if not self._proxies:
            return None
        now = self._clock()
        for _ in range(len(self._proxies)):
            proxy = self._proxies[self._cursor % len(self._proxies)]
            self._cursor += 1
            if self._banned_until.get(proxy, 0.0) <= now:
                return proxy
        # Everything is resting: use the one that recovers first rather than
        # silently falling back to the operator's own IP address.
        return min(self._proxies, key=lambda item: self._banned_until.get(item, 0.0))

    def report_failure(self, proxy: str | None) -> None:
        if proxy is not None:
            self._banned_until[proxy] = self._clock() + self._cooldown

    def report_success(self, proxy: str | None) -> None:
        if proxy is not None:
            self._banned_until.pop(proxy, None)


def _default_client_factory(proxy, headers, cookies, timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        proxy=proxy,
        headers=headers,
        cookies=cookies,
        timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
        follow_redirects=True,
    )


class _CurlClient:
    """Small adapter exposing ``get`` and ``cookies`` like httpx.AsyncClient.

    curl_cffi can send the TLS/HTTP2 handshake of a real browser, which plain
    httpx cannot. Responses are converted to httpx.Response and errors to httpx
    exceptions, so the fetcher's retry logic stays unchanged.
    """

    def __init__(self, impersonate, proxy, headers, cookies, timeout):
        from curl_cffi import requests as curl_requests  # optional dependency

        self._curl = curl_requests
        language = headers.get("Accept-Language")
        self._session = curl_requests.AsyncSession(
            impersonate=impersonate,
            # The impersonated browser supplies its own User-Agent and client
            # hints; sending ours would contradict the fingerprint.
            headers={"Accept-Language": language} if language else None,
            cookies=dict(cookies.items()) if cookies else None,
            proxies={"http": proxy, "https": proxy} if proxy else None,
            timeout=timeout,
        )

    @property
    def cookies(self) -> httpx.Cookies:
        jar = httpx.Cookies()
        for name, value in self._session.cookies.get_dict().items():
            jar.set(name, value)
        return jar

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self._session.close()

    async def get(self, url: str) -> httpx.Response:
        errors = self._curl.exceptions
        try:
            reply = await self._session.get(url, allow_redirects=True)
        except errors.Timeout as exc:
            raise httpx.ConnectTimeout(str(exc)) from exc
        except errors.RequestException as exc:
            raise httpx.ConnectError(str(exc)) from exc
        # curl_cffi already decoded the body: drop the headers that describe
        # the wire encoding so httpx does not try to decode it a second time.
        headers = [
            (key, value)
            for key, value in reply.headers.items()
            if key.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
        ]
        return httpx.Response(
            reply.status_code,
            headers=headers,
            content=reply.content,
            request=httpx.Request("GET", str(reply.url)),
        )


def make_client_factory(impersonate: str | None):
    """httpx by default; curl_cffi with a browser TLS fingerprint when asked."""
    if not impersonate:
        return _default_client_factory
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        raise ValueError(
            "MULTIMARKET_IMPERSONATE is set but curl_cffi is not installed: "
            "pip install -r backend/requirements-impersonate.txt"
        ) from None

    def factory(proxy, headers, cookies, timeout):
        return _CurlClient(impersonate, proxy, headers, cookies, timeout)

    return factory


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return None
    if value.isdigit():
        return min(float(value), MAX_RETRY_AFTER)
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = (moment - datetime.now(timezone.utc)).total_seconds()
    return min(max(delta, 0.0), MAX_RETRY_AFTER)


def looks_like_challenge(text: str) -> bool:
    if len(text) > CHALLENGE_MAX_CHARS:
        return False
    lowered = text.casefold()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


class ResilientFetcher:
    def __init__(
        self,
        config: FetcherConfig | None = None,
        *,
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
        sleep=asyncio.sleep,
        clock=time.monotonic,
        rng: random.Random | None = None,
    ):
        self.config = config or FetcherConfig()
        self._client_factory = client_factory or make_client_factory(self.config.impersonate)
        self._sleep = sleep
        self._clock = clock
        self._rng = rng or random.Random()
        self._pool = ProxyPool(self.config.proxies, self.config.proxy_cooldown, clock)
        self._profiles = browser_profiles()
        self._profile_index: dict[str, int] = {}
        self._cookies: dict[tuple[str, str | None], httpx.Cookies] = {}
        self._next_slot: dict[str, float] = {}
        self._cache: dict[str, tuple[float, FetchedPage]] = {}

    # -- politeness -------------------------------------------------------
    async def _throttle(self, host: str) -> None:
        # No await between reading and writing the slot, so concurrent tasks
        # on one event loop cannot claim the same slot.
        now = self._clock()
        ready = max(now, self._next_slot.get(host, 0.0))
        gap = self.config.min_interval + self._rng.uniform(0.0, self.config.jitter)
        self._next_slot[host] = ready + gap
        if ready > now:
            await self._sleep(ready - now)

    def _backoff(self, attempt: int) -> float:
        base = self.config.backoff_base * (2 ** attempt)
        return base + self._rng.uniform(0.0, self.config.backoff_base)

    # -- session state ----------------------------------------------------
    def _headers_for(self, host: str) -> dict[str, str]:
        index = self._profile_index.setdefault(
            host, self._rng.randrange(len(self._profiles))
        )
        headers = dict(self._profiles[index])
        if self.config.user_agent:
            headers = {
                key: value
                for key, value in headers.items()
                if not key.lower().startswith("sec-ch-")
            }
            headers["User-Agent"] = self.config.user_agent
        return headers

    def _reset_session(self, host: str, proxy: str | None) -> None:
        """Look like a fresh visitor after a block: new profile, no cookies."""
        self._cookies.pop((host, proxy), None)
        current = self._profile_index.get(host, 0)
        choices = [i for i in range(len(self._profiles)) if i != current]
        if choices:
            self._profile_index[host] = self._rng.choice(choices)

    # -- cache ------------------------------------------------------------
    def _cache_get(self, url: str) -> FetchedPage | None:
        entry = self._cache.get(url)
        if entry is None:
            return None
        if entry[0] <= self._clock():
            del self._cache[url]
            return None
        return entry[1]

    def _cache_put(self, url: str, page: FetchedPage) -> None:
        if self.config.cache_ttl <= 0:
            return
        if len(self._cache) >= 128:
            self._cache.pop(next(iter(self._cache)))
        self._cache[url] = (self._clock() + self.config.cache_ttl, page)

    # -- main entry point -------------------------------------------------
    async def _pause(self, delay: float, deadline: float) -> bool:
        """Sleep before the next attempt unless that would overrun the deadline."""
        if self._clock() + delay >= deadline:
            return False
        await self._sleep(delay)
        return True

    @staticmethod
    def _label(proxy: str | None) -> str:
        # Host only: proxy URLs usually carry credentials.
        return (urlparse(proxy).hostname or "proxy") if proxy else "direct"

    async def fetch(self, url: str) -> FetchedPage:
        cached = self._cache_get(url)
        if cached is not None:
            return cached

        host = urlparse(url).hostname or ""
        last_error: Exception | None = None
        attempts = max(1, self.config.max_attempts)
        deadline = self._clock() + self.config.total_timeout

        for attempt in range(attempts):
            is_last = attempt == attempts - 1
            await self._throttle(host)
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            proxy = self._pool.acquire()
            jar_key = (host, proxy)
            client = self._client_factory(
                proxy,
                self._headers_for(host),
                self._cookies.get(jar_key),
                self.config.timeout,
            )
            started = self._clock()
            try:
                async with client:
                    response = await asyncio.wait_for(client.get(url), timeout=remaining)
                    self._cookies[jar_key] = client.cookies
            except (httpx.RequestError, asyncio.TimeoutError) as exc:
                if isinstance(exc, asyncio.TimeoutError):
                    exc = httpx.ReadTimeout("fetch deadline exceeded")
                self._pool.report_failure(proxy)
                last_error = exc
                logger.warning(
                    "%s via %s: attempt %d/%d failed (%s: %s)",
                    host, self._label(proxy), attempt + 1, attempts,
                    type(exc).__name__, exc,
                )
                # Without another proxy to switch to, the same IP will simply
                # time out again: fail fast and report the real cause.
                if isinstance(exc, httpx.TimeoutException) and len(self._pool) < 2:
                    break
                if is_last or not await self._pause(self._backoff(attempt), deadline):
                    break
                continue

            status = response.status_code
            elapsed = self._clock() - started
            if status < 400:
                text = response.text
                if looks_like_challenge(text):
                    self._pool.report_failure(proxy)
                    self._reset_session(host, proxy)
                    last_error = BlockedError("challenge page instead of content", status)
                    logger.warning(
                        "%s via %s: attempt %d/%d got a challenge page (HTTP %d, %.1fs)",
                        host, self._label(proxy), attempt + 1, attempts, status, elapsed,
                    )
                    if is_last or not await self._pause(self._backoff(attempt), deadline):
                        break
                    continue
                self._pool.report_success(proxy)
                logger.debug("%s via %s: HTTP %d in %.1fs", host, self._label(proxy), status, elapsed)
                page = FetchedPage(str(response.url), text, status)
                self._cache_put(url, page)
                return page

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_error = exc
            logger.warning(
                "%s via %s: attempt %d/%d got HTTP %d (%.1fs)",
                host, self._label(proxy), attempt + 1, attempts, status, elapsed,
            )

            if status in BLOCK_STATUSES:
                self._pool.report_failure(proxy)
                self._reset_session(host, proxy)
            elif status not in RETRY_STATUSES:
                break  # 404 and similar: retrying will not help
            if is_last:
                break
            delay = _retry_after_seconds(response) if status in {429, 503} else None
            if not await self._pause(delay if delay is not None else self._backoff(attempt), deadline):
                break

        if last_error is None:
            last_error = httpx.ReadTimeout("fetch deadline exceeded")
        raise last_error


_shared: ResilientFetcher | None = None


def get_shared_fetcher() -> ResilientFetcher:
    """Process-wide fetcher so rate limits, cookies and proxy state are shared."""
    global _shared
    if _shared is None:
        _shared = ResilientFetcher(FetcherConfig.from_env())
    return _shared
