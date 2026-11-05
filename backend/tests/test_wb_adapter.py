import unittest

from src.parcers.wb_adapter import wb_record_to_offer


class WildberriesRecordMappingTests(unittest.TestCase):
    def test_maps_parser_item_fields(self):
        offer = wb_record_to_offer({
            "id": 123456,
            "name": "Кроссовки",
            "brand": "Example",
            "salePriceU": 2499.0,
            "priceU": 3999.0,
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
        self.assertIsNone(wb_record_to_offer({"id": "bad", "name": "Item", "salePriceU": 10}))

    def test_falls_back_to_regular_price(self):
        offer = wb_record_to_offer({
            "id": 12,
            "name": "Fallback item",
            "priceU": 500,
        })
        self.assertEqual(offer.price, 500.0)


if __name__ == "__main__":
    unittest.main()
