import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.parcers import monitoring
from src.parcers.api import app


class MonitoringApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patcher = patch.object(
            monitoring, "DB_PATH", Path(self.temp_dir.name) / "api.sqlite3"
        )
        self.path_patcher.start()
        monitoring.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.path_patcher.stop()
        self.temp_dir.cleanup()

    def test_monitor_lifecycle(self):
        response = self.client.post("/api/monitors", json={
            "query": "coffee machine",
            "product_url": "https://www.ozon.ru/product/item-1",
            "marketplace": "Ozon",
            "title": "Coffee machine",
            "interval_seconds": 900,
        })
        self.assertEqual(response.status_code, 201)
        monitor_id = response.json()["id"]

        listed = self.client.get("/api/monitors")
        self.assertEqual(len(listed.json()["monitors"]), 1)

        paused = self.client.patch(
            f"/api/monitors/{monitor_id}", json={"active": False}
        )
        self.assertEqual(paused.status_code, 200)
        self.assertFalse(paused.json()["active"])

        history = self.client.get(f"/api/monitors/{monitor_id}/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["points"], [])

        exported = self.client.get("/api/monitors/export.csv")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("Coffee machine", exported.text)

        deleted = self.client.delete(f"/api/monitors/{monitor_id}")
        self.assertEqual(deleted.status_code, 200)

    def test_monitor_requires_https_valid_domain_and_minimum_interval(self):
        cases = [
            {"query": "item", "product_url": "http://www.ozon.ru/product/1",
             "marketplace": "Ozon", "title": "Item", "interval_seconds": 900},
            {"query": "item", "product_url": "https://market.example/item",
             "marketplace": "Ozon", "title": "Item", "interval_seconds": 900},
            {"query": "item", "product_url": "https://www.ozon.ru/product/1",
             "marketplace": "Ozon", "title": "Item", "interval_seconds": 10},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/monitors", json=payload)
                self.assertEqual(response.status_code, 422)

    def test_batch_search_accepts_multiple_queries(self):
        with patch("src.parcers.api.search_service.search", new_callable=AsyncMock) as search:
            search.side_effect = [
                {"query": "coffee machine"},
                {"query": "wireless headphones"},
            ]
            response = self.client.post("/api/search/batch", json={
                "queries": ["coffee machine", "wireless headphones"],
                "limit": 5,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(search.await_count, 2)
        self.assertEqual(
            [item["query"] for item in response.json()["results"]],
            ["coffee machine", "wireless headphones"],
        )


if __name__ == "__main__":
    unittest.main()
