import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from src.parcers.api import app
from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.feed import JsonFeedAdapter
from src.parcers.product_data import delivery_data, image_urls, schema_delivery
from src.parcers.public_html import PublicHtmlSearchAdapter
from src.parcers.service import MarketplaceSearchService
from src.parcers.ym import YandexMarketAdapter


class RichProductDataTests(unittest.TestCase):
    def test_images_are_safe_deduplicated_and_bounded(self):
        self.assertEqual(image_urls(["https://cdn.example/a", {"url": "https://cdn.example/a"},
                                     "javascript:alert(1)", "https://user:pass@cdn.example/b", "/b"],
                                    "https://cdn.example/item"),
                         ["https://cdn.example/a", "https://cdn.example/b"])
        self.assertEqual(len(image_urls([f"https://cdn.example/{i}" for i in range(50)])), 20)

    def test_schema_delivery_adds_handling_and_transit_without_mixing_regions(self):
        value = {"shippingDetails": [{"shippingDestination": {"addressRegion": "Москва"},
            "shippingRate": {"value": 0, "currency": "RUB"}, "deliveryTime": {
                "handlingTime": {"minValue": 1, "maxValue": 2, "unitCode": "DAY"},
                "transitTime": {"minValue": 2, "maxValue": 5, "unitCode": "DAY"}}},
            {"shippingDestination": {"addressRegion": "Казань"}, "shippingRate": {"value": 500, "currency": "RUB"}}]}
        self.assertEqual(schema_delivery(value), {"min_days": 3, "max_days": 7,
            "destination": "Москва", "cost": 0.0, "currency": "RUB"})

    def test_partial_or_unsupported_delivery_is_not_a_total_days_promise(self):
        partial = schema_delivery({"shippingDetails": {"deliveryTime": {
            "transitTime": {"maxValue": 2, "unitCode": "DAY"}}}})
        self.assertNotIn("max_days", partial)
        self.assertIn("В пути", partial["text"])
        self.assertEqual(schema_delivery({"shippingDetails": {"deliveryTime": {
            "transitTime": {"maxValue": 48, "unitCode": "HUR"}}}}), {})

    def test_delivery_rejects_invalid_ranges_and_keeps_free_shipping(self):
        self.assertEqual(delivery_data({"min_days": 7, "max_days": 2, "cost": 0, "currency": "RUB"}),
                         {"cost": 0.0, "currency": "RUB"})
        self.assertEqual(delivery_data({"max_days": True, "cost": "nan", "latest_date": "not-a-date"}), {})

    def test_public_product_retains_gallery_more_reviews_and_characteristics(self):
        adapter = PublicHtmlSearchAdapter(marketplace="Ozon", search_url="https://www.ozon.ru/search/?text={query}", allowed_hosts=("ozon.ru",))
        product = {"@type": "Product", "name": "Товар", "url": "https://www.ozon.ru/product/item/",
            "image": ["https://cdn.example/a", {"url": "https://cdn.example/b"}],
            "review": [{"reviewBody": f"Отзыв {i}"} for i in range(23)],
            "additionalProperty": [{"name": f"Параметр {i}", "value": str(i)} for i in range(45)],
            "offers": {"price": 100, "priceCurrency": "RUB", "shippingDetails": {
                "shippingRate": {"value": 0, "currency": "RUB"}}}}
        html = '<script type="application/ld+json">' + json.dumps(product) + '</script>'
        offer = adapter._extract_product(html, product["url"])
        self.assertEqual(len(offer.reviews), 23)
        self.assertEqual(len(offer.specifications), 45)
        self.assertEqual(offer.image_urls, ["https://cdn.example/a", "https://cdn.example/b"])
        self.assertEqual(offer.delivery["cost"], 0)

    def test_feed_carries_more_than_ten_reviews_images_and_delivery(self):
        adapter = JsonFeedAdapter(marketplace="Ozon", base_search_url="https://www.ozon.ru/search/?text={query}",
            reason="test", feed_url="https://feed.example/items", allowed_hosts=("ozon.ru",))
        offer = adapter._map_offer({"title": "Товар", "price": 100, "url": "https://www.ozon.ru/product/item/",
            "images": ["https://cdn.example/a", "https://cdn.example/b"], "delivery": {"max_days": 2},
            "reviews": [{"body": f"Отзыв {i}"} for i in range(25)]})
        self.assertEqual(len(offer.reviews), 25)
        self.assertEqual(len(offer.image_urls), 2)
        self.assertEqual(offer.delivery, {"max_days": 2})

    def test_product_jsonld_is_not_replaced_by_search_recommendations(self):
        class Adapter(PublicHtmlSearchAdapter):
            def _extract(self, html, page_url, limit):
                return []  # A search-only override must not hide Product JSON-LD.
        adapter = Adapter(marketplace="Ozon", search_url="https://www.ozon.ru/search/?text={query}", allowed_hosts=("ozon.ru",))
        html = '<script type="application/ld+json">' + json.dumps({"@type":"Product", "name":"Товар", "url":"https://www.ozon.ru/product/own/", "offers":{"price":100}}) + '</script>'
        self.assertEqual(adapter._extract_product(html, "https://www.ozon.ru/product/own/").title, "Товар")

    def test_yandex_product_gallery_is_scoped_to_product_markup(self):
        adapter = YandexMarketAdapter(marketplace="Яндекс Маркет", search_url="https://market.yandex.ru/search?text={query}", allowed_hosts=("market.yandex.ru",))
        html = ('<img src="https://cdn.example/logo"><h1 data-auto="productCardTitle">Товар</h1>'
            '<span data-auto="snippet-price-current">100 ₽</span><div data-zone-name="ProductGallery">'
            '<img src="https://cdn.example/one"><img src="https://cdn.example/two"></div>'
            '<div data-auto="delivery-estimate">Доставка 15 ноября</div>')
        offer = adapter._extract_product(html, "https://market.yandex.ru/card/item/123")
        self.assertEqual(offer.image_urls, ["https://cdn.example/one", "https://cdn.example/two"])
        self.assertEqual(offer.delivery, {"text": "Доставка 15 ноября"})

    def test_search_and_details_api_preserve_enriched_fields(self):
        offer = Offer(marketplace="Ozon", title="Товар", price=100, currency="RUB",
                      url="https://www.ozon.ru/product/item/", image_urls=["https://cdn.example/a"],
                      brand="Example", delivery={"max_days": 3}, reviews=[{"body": f"Отзыв {i}"} for i in range(23)])
        class Adapter:
            marketplace = "Ozon"
            async def search(self, query, limit):
                return ProviderResult("Ozon", SearchStatus.READY, "https://www.ozon.ru/search/", [offer])
        result = asyncio.run(MarketplaceSearchService(adapters=[Adapter()]).search("товар"))
        self.assertEqual(result["products"][0]["offers"][0]["delivery"], {"max_days": 3})
        self.assertEqual(result["products"][0]["offers"][0]["brand"], "Example")
        with patch("src.parcers.api.search_service.parse_product", new_callable=AsyncMock) as parser:
            client = TestClient(app)
            parser.return_value = offer
            payload = client.get("/api/product-details", params={"marketplace": "Ozon", "product_url": offer.url}).json()
            client.close()
        self.assertEqual(len(payload["reviews"]), 23)
        self.assertEqual(payload["image_urls"], ["https://cdn.example/a"])


if __name__ == "__main__":
    unittest.main()
