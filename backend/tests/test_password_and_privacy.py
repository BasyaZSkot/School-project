from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.parcers import accounts, monitoring
from src.parcers.api import app


class PasswordAndPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.directory.name) / "test.sqlite3"
        self.patcher = patch.object(monitoring, "DB_PATH", self.db_path)
        self.patcher.start()
        monitoring.init_db()
        self.a = TestClient(app)
        self.b = TestClient(app)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)

    def csrf(self, client):
        return {"X-CSRF-Token": client.get("/api/auth/me").json()["csrf_token"]}

    def register(self, client, email):
        response = client.post("/api/auth/register", json={
            "name": "User", "email": email, "password": "a strong password"
        }, headers=self.csrf(client))
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn("password", str(response.json()))
        client.headers.update(self.csrf(client))
        return response.json()["user"]

    def create(self, client, suffix="same", title="same"):
        response = client.post("/api/monitors", json={
            "query": "item", "product_url": "https://www.ozon.ru/product/" + suffix,
            "marketplace": "Ozon", "title": title, "interval_seconds": 900,
            "user_id": "forged-owner",
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_register_logout_login_and_password_storage(self):
        user = self.register(self.a, "  USER@example.test ")
        self.assertEqual(user["email"], "user@example.test")
        self.assertEqual(user["role"], "user")
        with closing(sqlite3.connect(self.db_path)) as db, db:
            stored = db.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("a strong password", stored)
        self.assertEqual(self.a.post("/auth/logout").status_code, 200)
        self.assertFalse(self.a.get("/api/auth/me").json()["authenticated"])
        headers = self.csrf(self.a)
        wrong = self.a.post("/api/auth/login", headers=headers, json={
            "email": "user@example.test", "password": "wrong"
        })
        self.assertEqual(wrong.status_code, 401)
        correct = self.a.post("/api/auth/login", headers=headers, json={
            "email": "USER@example.test", "password": "a strong password"
        })
        self.assertEqual(correct.status_code, 200)
        self.assertEqual(correct.json()["user"]["id"], user["id"])

    def test_validation_duplicate_and_csrf(self):
        self.assertEqual(self.a.post("/api/auth/register", json={
            "name": "User", "email": "user@example.test", "password": "password"
        }).status_code, 403)
        for email, password, name in [("bad", "password", "User"),
                                       ("user@example.test", "short", "User"),
                                       ("user@example.test", "password", " ")]:
            result = self.a.post("/api/auth/register", headers=self.csrf(self.a),
                                 json={"email": email, "password": password, "name": name})
            self.assertEqual(result.status_code, 400)
        self.register(self.a, "user@example.test")
        duplicate = self.b.post("/api/auth/register", headers=self.csrf(self.b), json={
            "name": "Other", "email": "USER@example.test", "password": "another-password"
        })
        self.assertEqual(duplicate.status_code, 400)
        self.assertFalse(self.b.get("/api/auth/me").json()["authenticated"])

    def test_two_accounts_cannot_read_or_change_each_others_monitors(self):
        user = self.register(self.a, "a@example.test")
        self.register(self.b, "b@example.test")
        a = self.create(self.a, title="Only user A")
        b = self.create(self.b, title="Only user B")
        self.assertEqual(a["user_id"], user["id"])
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(self.a.post("/api/monitors", json={
            "query": "item", "product_url": a["product_url"], "marketplace": "Ozon",
            "title": "duplicate", "interval_seconds": 900,
        }).status_code, 409)
        for monitor in (a, b):
            monitoring.record_check(monitor["id"], price=100, currency="RUB", status="ok")
            monitoring.record_check(monitor["id"], price=80, currency="RUB", status="ok")
        monitoring.create_monitor(query="legacy", product_url="https://www.ozon.ru/legacy",
                                  marketplace="Ozon", title="legacy-secret", interval_seconds=900)
        for client, own, other in ((self.a, a, b), (self.b, b, a)):
            self.assertEqual([m["id"] for m in client.get("/api/monitors").json()["monitors"]], [own["id"]])
            self.assertEqual(client.get(f"/api/monitors/{other['id']}/history").status_code, 404)
            self.assertEqual(client.patch(f"/api/monitors/{other['id']}", json={"active": False}).status_code, 404)
            self.assertEqual(client.delete(f"/api/monitors/{other['id']}").status_code, 404)
            self.assertEqual(client.get("/api/alerts", params={"monitor_id": other["id"]}).status_code, 404)
            alerts = client.get("/api/alerts").json()["alerts"]
            self.assertEqual([alert["monitor_id"] for alert in alerts], [own["id"]])
            exported = client.get("/api/monitors/export.csv").text
            self.assertIn(own["title"], exported)
            self.assertNotIn(other["title"], exported)
            self.assertNotIn("legacy-secret", exported)
            self.assertEqual(client.get("/api/monitors").headers["cache-control"], "no-store")
        accounts.set_role(user["id"], "admin")
        self.assertEqual(len(self.a.get("/api/monitors").json()["monitors"]), 1)
        self.a.headers.pop("X-CSRF-Token")
        self.assertEqual(self.a.delete(f"/api/monitors/{a['id']}").status_code, 403)

    def test_guests_cannot_access_private_data(self):
        for url in ("/api/monitors", "/api/monitors/export.csv", "/api/monitors/other/history", "/api/alerts"):
            self.assertEqual(self.a.get(url).status_code, 401)
        for url in ("/monitoring", "/history"):
            response = self.a.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
        self.assertEqual(self.a.delete("/api/monitors/other").status_code, 401)
        self.assertEqual(self.a.patch("/api/monitors/other", json={"active": False}).status_code, 401)

    def test_login_throttles_repeated_attempts(self):
        headers = self.csrf(self.a)
        for _ in range(10):
            self.assertEqual(self.a.post("/api/auth/login", headers=headers, json={
                "email": "unknown@example.test", "password": "wrong"
            }).status_code, 401)
        self.assertEqual(self.a.post("/api/auth/login", headers=headers, json={
            "email": "unknown@example.test", "password": "wrong"
        }).status_code, 429)

    def test_migration_preserves_legacy_history_and_is_repeatable(self):
        # Recreate the original global table with its original foreign keys.
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("DROP TABLE price_alerts")
            db.execute("DROP TABLE price_snapshots")
            db.execute("DROP TABLE monitors")
            db.execute("""CREATE TABLE monitors (
                id TEXT PRIMARY KEY, query TEXT NOT NULL, product_url TEXT NOT NULL,
                marketplace TEXT NOT NULL, title TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, current_price REAL, currency TEXT,
                last_checked_at TEXT, next_run_at TEXT NOT NULL, last_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL, UNIQUE(product_url))""")
        # Create original child tables before running the migration.
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("CREATE TABLE price_snapshots (id INTEGER PRIMARY KEY, monitor_id TEXT REFERENCES monitors(id) ON DELETE CASCADE, price REAL, currency TEXT, captured_at TEXT)")
            db.execute("INSERT INTO monitors (id, query, product_url, marketplace, title, interval_seconds, next_run_at, created_at) VALUES ('old', 'q', 'https://www.ozon.ru/old', 'Ozon', 'Old', 900, '2020', '2020')")
            db.execute("INSERT INTO price_snapshots VALUES (1, 'old', 100, 'RUB', '2020')")
        monitoring.init_db()
        monitoring.init_db()
        self.assertIsNone(monitoring.get_monitor("old")["user_id"])
        self.assertEqual(monitoring.price_history("old")[0]["price"], 100)
        self.assertEqual(monitoring.due_monitors(), [])
        self.register(self.a, "a@example.test")
        self.assertEqual(self.a.get("/api/monitors").json()["monitors"], [])
        self.assertTrue(monitoring.delete_monitor("old"))
        self.assertEqual(monitoring.price_history("old"), [])
