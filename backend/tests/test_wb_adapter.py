import unittest

from src.parcers.wb_adapter import wb_record_to_offer


class WildberriesRecordMappingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
