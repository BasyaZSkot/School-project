import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.parcers.api import app
from src.parcers.base import Offer


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

    def test_search_accepts_limit_of_two_hundred(self):
        expected = {"query": "phone", "providers": [], "products": [], "has_more": False}
        with patch("src.parcers.api.search_service.search", new_callable=AsyncMock) as mocked:
            mocked.return_value = expected
            response = self.client.get("/api/search", params={"q": "phone", "limit": 200})

        self.assertEqual(response.status_code, 200)
        mocked.assert_awaited_once_with("phone", 200, 0)


    def test_search_passes_session_id_for_stable_pagination(self):
        expected = {"query": "phone", "providers": [], "products": [], "has_more": False}
        with patch("src.parcers.api.search_service.search", new_callable=AsyncMock) as mocked:
            mocked.return_value = expected
            response = self.client.get("/api/search", params={
                "q": "phone", "session_id": "session-test-123",
            })
        self.assertEqual(response.status_code, 200)
        mocked.assert_awaited_once_with("phone", 20, 0, session_id="session-test-123")

    def test_product_details_returns_public_metadata(self):
        offer = Offer(
            marketplace="Ozon",
            title="Наушники Example",
            price=4590,
            currency="RUB",
            url="https://www.ozon.ru/product/headphones-777/",
            description="Беспроводные наушники.",
            rating=4.7,
            review_count=123,
            specifications=[{"name": "Цвет", "value": "Чёрный"}],
        )
        with patch("src.parcers.api.search_service.parse_product", new_callable=AsyncMock) as mocked:
            mocked.return_value = offer
            response = self.client.get("/api/product-details", params={
                "marketplace": "Ozon", "product_url": offer.url,
            })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["details_available"])
        self.assertEqual(payload["description"], "Беспроводные наушники.")
        self.assertEqual(payload["rating"], 4.7)
        self.assertEqual(payload["review_count"], 123)
        mocked.assert_awaited_once_with("Ozon", offer.url)

    def test_product_details_rejects_other_hosts(self):
        with patch("src.parcers.api.search_service.parse_product", new_callable=AsyncMock) as mocked:
            response = self.client.get("/api/product-details", params={
                "marketplace": "Ozon", "product_url": "https://evil.example/product/1",
            })
        self.assertEqual(response.status_code, 422)
        mocked.assert_not_awaited()

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
