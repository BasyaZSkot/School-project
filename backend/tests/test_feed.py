import unittest

from src.parcers.feed import JsonFeedAdapter


class JsonFeedAdapterMappingTests(unittest.TestCase):
    def setUp(self):
        self.adapter = JsonFeedAdapter(
            marketplace="Test Market",
            base_search_url="https://example.org/search?q={query}",
            reason="feed not configured",
            feed_url="https://partner.example/api/search",
        )

    def test_maps_valid_normalized_offer(self):
        offer = self.adapter._map_offer({
            "id": "42",
            "title": "Sample item",
            "price": "1299.50",
            "currency": "rub",
            "url": "https://market.example/item/42",
            "image_url": "https://img.example/item.webp",
            "in_stock": True,
        })
        self.assertIsNotNone(offer)
        self.assertEqual(offer.price, 1299.5)
        self.assertEqual(offer.currency, "RUB")
        self.assertEqual(offer.marketplace, "Test Market")

    def test_rejects_non_https_product_urls(self):
        self.assertIsNone(self.adapter._map_offer({
            "id": "1", "title": "Bad", "price": 10, "currency": "RUB",
            "url": "http://market.example/item/1",
        }))

    def test_rejects_invalid_prices(self):
        self.assertIsNone(self.adapter._map_offer({
            "id": "1", "title": "Bad", "price": -1, "currency": "RUB",
            "url": "https://market.example/item/1",
        }))

    def test_requires_https_feed_endpoint(self):
        with self.assertRaises(ValueError):
            JsonFeedAdapter(
                marketplace="Bad", base_search_url="https://example.org/{query}",
                reason="bad", feed_url="http://localhost/feed",
            )


if __name__ == "__main__":
    unittest.main()
