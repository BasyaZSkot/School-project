import unittest

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
        response = self.client.get("/api/search", params={"q": "кофемашина"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["providers"]), 3)
        self.assertEqual(payload["total_offers"], 0)
        self.assertEqual(payload["products"], [])
        self.assertTrue(all(provider["search_url"].startswith("https://") for provider in payload["providers"]))

    def test_search_rejects_blank_and_invalid_limit(self):
        self.assertEqual(self.client.get("/api/search", params={"q": "   "}).status_code, 400)
        self.assertEqual(self.client.get("/api/search", params={"q": "item", "limit": 0}).status_code, 422)

    def test_homepage_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("MultiMarket", response.text)


if __name__ == "__main__":
    unittest.main()
