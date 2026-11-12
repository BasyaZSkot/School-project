import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.parcers.api import app
from src.parcers import monitoring


class AuthAndAdminApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "accounts.sqlite3"
        self.db_patch = patch.object(monitoring, "DB_PATH", db_path)
        self.db_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_private_pages_and_admin_api_require_login(self):
        account = self.client.get("/account", follow_redirects=False)
        admin = self.client.get("/admin", follow_redirects=False)
        users = self.client.get("/api/admin/users")

        self.assertEqual(account.status_code, 303)
        self.assertIn("/login?next=/account", account.headers["location"])
        self.assertEqual(admin.status_code, 303)
        self.assertIn("/login?next=/admin", admin.headers["location"])
        self.assertEqual(users.status_code, 401)

    def _oauth_start(self, provider="google", next_path="/account"):
        env = {
            "GOOGLE_CLIENT_ID": "google-client-id",
            "GOOGLE_CLIENT_SECRET": "google-client-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
            "YANDEX_CLIENT_ID": "yandex-client-id",
            "YANDEX_CLIENT_SECRET": "yandex-client-secret",
            "YANDEX_REDIRECT_URI": "http://localhost:8000/auth/yandex/callback",
        }
        with patch.dict(os.environ, env):
            response = self.client.get(
                f"/auth/{provider}", params={"next": next_path}, follow_redirects=False
            )
        return response, parse_qs(urlparse(response.headers["location"]).query)

    def _login(self, email, next_path="/account"):
        start, params = self._oauth_start(next_path=next_path)
        state = params["state"][0]
        with (
            patch.dict(os.environ, {
                "GOOGLE_CLIENT_ID": "google-client-id",
                "GOOGLE_CLIENT_SECRET": "google-client-secret",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
                "MULTIMARKET_ADMIN_EMAILS": "admin@example.test",
            }),
            patch("src.parcers.api.oauth.fetch_profile", new_callable=AsyncMock) as fetch_profile,
        ):
            fetch_profile.return_value = {
                "subject": "google-subject-1",
                "email": email,
                "name": "Example User",
                "picture_url": None,
            }
            callback = self.client.get(
                "/auth/google/callback",
                params={"code": "authorization-code", "state": state},
                follow_redirects=False,
            )
        self.assertEqual(start.status_code, 302)
        fetch_profile.assert_awaited_once()
        return callback

    def test_google_login_creates_session_and_bootstraps_admin(self):
        callback = self._login("admin@example.test", "/admin")
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(callback.headers["location"], "/admin")

        admin_page = self.client.get("/admin")
        users = self.client.get("/api/admin/users").json()["users"]
        me = self.client.get("/api/auth/me").json()

        self.assertEqual(admin_page.status_code, 200)
        self.assertEqual(admin_page.headers["cache-control"], "no-store")
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["role"], "admin")
        self.assertTrue(me["authenticated"])
        self.assertNotIn("subject", me["user"])
        self.assertTrue(me["csrf_token"])

    def test_oauth_callback_rejects_mismatched_state(self):
        start, params = self._oauth_start()
        self.assertEqual(start.status_code, 302)
        with patch("src.parcers.api.oauth.fetch_profile", new_callable=AsyncMock) as fetch_profile:
            response = self.client.get(
                "/auth/google/callback",
                params={"code": "authorization-code", "state": "wrong-state"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 400)
        fetch_profile.assert_not_awaited()

    def test_oauth_return_path_cannot_redirect_to_another_site(self):
        _, params = self._oauth_start(next_path="https://evil.example/path")
        with (
            patch.dict(os.environ, {
                "GOOGLE_CLIENT_ID": "google-client-id",
                "GOOGLE_CLIENT_SECRET": "google-client-secret",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
            }),
            patch("src.parcers.api.oauth.fetch_profile", new_callable=AsyncMock) as fetch_profile,
        ):
            fetch_profile.return_value = {
                "subject": "google-subject-1",
                "email": "user@example.test",
                "name": "Example User",
                "picture_url": None,
            }
            response = self.client.get(
                "/auth/google/callback",
                params={"code": "authorization-code", "state": params["state"][0]},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account")

    def test_regular_account_cannot_open_admin_panel_or_api(self):
        callback = self._login("member@example.test")
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/users").status_code, 403)

    def test_admin_role_changes_require_csrf_and_cannot_remove_last_admin(self):
        self._login("admin@example.test")
        user = self.client.get("/api/admin/users").json()["users"][0]
        without_csrf = self.client.patch(
            f"/api/admin/users/{user['id']}", json={"role": "user"}
        )
        csrf = self.client.get("/api/auth/me").json()["csrf_token"]
        self_demote = self.client.patch(
            f"/api/admin/users/{user['id']}",
            json={"role": "user"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(without_csrf.status_code, 403)
        self.assertEqual(self_demote.status_code, 409)


if __name__ == "__main__":
    unittest.main()

