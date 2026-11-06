import unittest
from unittest.mock import AsyncMock, Mock, patch

from src.parcers.feed import JsonFeedAdapter
from src.parcers.wb_adapter import wb_record_to_offer


class PartnerFeedAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_wb_native_product_records(self):
        adapter = JsonFeedAdapter(
            marketplace="Wildberries",
            base_search_url="https://www.wildberries.ru/catalog/0/search.aspx?search={query}",
            reason="feed unavailable",
            feed_url="https://partner.example/api/search",
            records_key="products",
            record_mapper=wb_record_to_offer,
        )
        response = Mock()
        response.json.return_value = {"products": [
            {"id": 123, "name": "Тестовый товар", "salePriceU": 159900}
        ]}
        response.raise_for_status.return_value = None
        client = AsyncMock()
        client.get.return_value = response

        with patch("src.parcers.feed.httpx.AsyncClient") as client_type:
            client_type.return_value.__aenter__.return_value = client
            result = await adapter.search("товар", 10)

        self.assertEqual(result.status.value, "ready")
        self.assertEqual(len(result.offers), 1)
        self.assertEqual(result.offers[0].price, 1599.0)
        self.assertEqual(result.offers[0].external_id, "123")

    async def test_rejects_non_https_feed_url(self):
        with self.assertRaises(ValueError):
            JsonFeedAdapter(
                marketplace="Wildberries",
                base_search_url="https://example.com/?q={query}",
                reason="disabled",
                feed_url="http://partner.example/feed",
            )


if __name__ == "__main__":
    unittest.main()
