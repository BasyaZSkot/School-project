import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.parcers.api import app


class MarketplaceApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_search_returns_provider_links_and_no_fake_prices(self):
        expected = {
            "query": "кофемашина",
            "providers": [
                {"marketplace": name, "status": "no_results", "search_url": url,
                 "offers": [], "message": "No public cards"}
                for name, url in [
                    ("Ozon", "https://www.ozon.ru/search/?text=test"),
                    ("Wildberries", "https://www.wildberries.ru/catalog/0/search.aspx?search=test"),
                    ("Яндекс Маркет", "https://market.yandex.ru/search?text=test"),
                ]
            ],
            "products": [],
            "total_offers": 0,
            "notice": "No offers",
        }
        with patch("src.parcers.api.search_service.search", new_callable=AsyncMock) as mocked:
            mocked.return_value = expected
            response = self.client.get("/api/search", params={"q": "кофемашина"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["providers"]), 3)
        self.assertEqual(payload["total_offers"], 0)
        self.assertEqual(payload["products"], [])
        self.assertTrue(all(provider["search_url"].startswith("https://") for provider in payload["providers"]))
        mocked.assert_awaited_once_with("кофемашина", 20, 0)

    def test_search_rejects_blank_and_invalid_limit(self):
        self.assertEqual(self.client.get("/api/search", params={"q": "   "}).status_code, 400)
        self.assertEqual(self.client.get("/api/search", params={"q": "item", "limit": 0}).status_code, 422)

    def test_homepage_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("MultiMarket", response.text)

    def test_navigation_pages_are_served_separately(self):
        for path in ("/monitoring", "/history", "/sources"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("<html", response.text)


if __name__ == "__main__":
    unittest.main()
