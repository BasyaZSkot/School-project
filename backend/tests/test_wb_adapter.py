import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import AsyncMock

from src.parcers.wb_adapter import WildberriesAdapter, wb_record_to_offer


class WildberriesRecordMappingTests(unittest.TestCase):
    def test_item_model_prices_are_already_rubles_and_all_images_are_preserved(self):
        item = SimpleNamespace(id=1241343962, name='Кроссовки Air Force 1', salePriceU=3328.0,
            priceU=10350.0, wb_wallet=3261, brand='Nike', supplier='BOSTON', totalQuantity=35,
            reviewRating=4.8, feedbacks=581, sizes=[],
            image_links='\u200bhttps://basket-41.wbbasket.ru/1.webp;https://basket-41.wbbasket.ru/2.webp')
        offer = wb_record_to_offer(item, prices_in_rubles=True)
        self.assertEqual(offer.price, 3328.0)
        self.assertEqual(offer.seller, 'BOSTON')
        self.assertEqual(len(offer.image_urls), 2)
        self.assertEqual(offer.rating, 4.8)
        self.assertEqual(offer.review_count, 581)
        self.assertTrue(offer.in_stock)

    def test_items_source_is_connected_to_site_search_and_capped(self):
        import asyncio
        from src.parcers.wb import WildberriesAdapter as PublicAdapter
        from src.parcers.service import MarketplaceSearchService
        items = [SimpleNamespace(id=i+1, name=f'Item {i}', salePriceU=3328.0) for i in range(210)]
        source = AsyncMock(return_value=items)
        with patch.dict(os.environ, {'MULTIMARKET_WB_SOURCE': 'items'}), patch('src.parcers.wb_items.fetch_items', source):
            adapter = PublicAdapter.from_env()
            result = asyncio.run(adapter.search('test', 200))
            self.assertEqual(len(result.offers), 200)
            service = MarketplaceSearchService(adapters=[adapter], enabled_search_marketplaces={'Wildberries'})
            data = asyncio.run(service.search('test', limit=20))
            self.assertTrue(data['products'])
            self.assertEqual(data['products'][0]['offers'][0]['price'], 3328.0)

    def test_maps_parser_item_fields_and_converts_kopecks(self):
        offer = wb_record_to_offer({
            "id": 123456,
            "name": "Кроссовки",
            "brand": "Example",
            "salePriceU": 249900,
            "priceU": 399900,
            "totalQuantity": 7,
            "image_links": "\u200bhttps://example.org/image.webp",
        })

        self.assertIsNotNone(offer)
        self.assertEqual(offer.marketplace, "Wildberries")
        self.assertEqual(offer.price, 2499.0)
        self.assertEqual(offer.currency, "RUB")
        self.assertEqual(offer.external_id, "123456")
        self.assertTrue(offer.in_stock)
        self.assertEqual(offer.image_url, "https://example.org/image.webp")

    def test_maps_wb_description_reviews_rating_and_characteristics(self):
        offer = wb_record_to_offer({
            "id": 321,
            "name": "Кружка Example",
            "salePriceU": 159900,
            "description": "Керамическая кружка.",
            "reviewRating": 4.6,
            "feedbacks": 34,
            "characteristics": '{"Объём":"350 мл","Цвет":"Синий"}',
        })
        self.assertIsNotNone(offer)
        self.assertEqual(offer.description, "Керамическая кружка.")
        self.assertEqual(offer.rating, 4.6)
        self.assertEqual(offer.review_count, 34)
        self.assertEqual(offer.specifications, [
            {"name": "Объём", "value": "350 мл"},
            {"name": "Цвет", "value": "Синий"},
        ])

    def test_rejects_missing_identity_or_price(self):
        self.assertIsNone(wb_record_to_offer({"id": 12, "name": "No price"}))
        self.assertIsNone(wb_record_to_offer({"id": "bad", "name": "Item", "salePriceU": 1000}))

    def test_falls_back_to_regular_price(self):
        offer = wb_record_to_offer({
            "id": 12,
            "name": "Fallback item",
            "priceU": 50000,
        })
        self.assertEqual(offer.price, 500.0)

    def test_reads_nested_size_price(self):
        offer = wb_record_to_offer({
            "id": 13,
            "name": "Nested item",
            "sizes": [{"price": {"product": 123450}}],
        })
        self.assertEqual(offer.price, 1234.5)

    def test_adapter_accepts_an_explicit_approved_async_source(self):
        source = AsyncMock(return_value=[{
            "id": 99,
            "name": "Source item",
            "salePriceU": 159900,
        }])
        adapter = WildberriesAdapter.from_record_source(source)
        self.assertIs(adapter.source, source)

    def test_factory_rejects_non_callable_source(self):
        with self.assertRaises(TypeError):
            WildberriesAdapter.from_record_source(None)

    def test_injected_source_records_are_normalized(self):
        import asyncio

        async def source(query, limit):
            self.assertEqual(query, "кроссовки")
            self.assertEqual(limit, 5)
            return [{"id": 100, "name": "Кроссовки", "salePriceU": 199900}]

        adapter = WildberriesAdapter.from_record_source(source)
        result = asyncio.run(adapter.search("кроссовки", limit=5))
        self.assertEqual(result.status.value, "ready")
        self.assertEqual(len(result.offers), 1)
        self.assertEqual(result.offers[0].price, 1999.0)


if __name__ == "__main__":
    unittest.main()
