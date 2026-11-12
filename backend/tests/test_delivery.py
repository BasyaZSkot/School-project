from datetime import date
from pathlib import Path
import unittest

from src.parcers.product_data import delivery_data, schema_delivery
from src.parcers.yandex_delivery import extract_yandex_deliveries
from src.parcers.ym import YandexMarketAdapter


class DeliveryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.html = (Path(__file__).parent / "fixtures/yandex_delivery.html").read_text(encoding="utf-8")
        self.reference = date(2026, 11, 12)
        self.adapter = YandexMarketAdapter(marketplace="Яндекс Маркет", search_url="https://market.yandex.ru/search?text={query}", allowed_hosts=("market.yandex.ru",))

    def test_real_search_delivery_marker_and_upper_date_are_preserved(self):
        offers = self.adapter._extract(self.html, "https://market.yandex.ru/search?text=test", 20)
        self.assertEqual(offers[0].delivery["earliest_date"], "2026-11-20")
        self.assertEqual(offers[0].delivery["latest_date"], "2026-11-25")
        self.assertNotIn("max_days", offers[0].delivery)  # deliveryDays:8 was the first date, not the upper bound.
        self.assertEqual(offers[0].delivery["destination"], "Санкт-Петербург")

    def test_product_delivery_is_read_from_its_own_console(self):
        offer = self.adapter._extract_product(self.html, "https://market.yandex.ru/card/headphones/123")
        self.assertEqual(offer.delivery["latest_date"], "2026-11-14")
        self.assertEqual(offer.delivery["cost"], 0)
        self.assertEqual(offer.delivery["currency"], "RUB")
        self.assertEqual(offer.delivery["method"], "По клику")

    def test_recommendation_delivery_does_not_become_the_product_delivery(self):
        html = '<div data-zone-name="productSnippet"><div data-auto="delivery-wrapper" data-zone-data=\'{"deliveryDateTo":"2026-11-30"}\'>30 ноября</div></div>'
        _, primary = extract_yandex_deliveries(html)
        self.assertEqual(primary, {})

    def test_malformed_zone_json_falls_back_to_visible_text(self):
        html = '<div data-auto="searchOrganic"><a href="/card/item/1">Товар</a><div data-auto="delivery-wrapper" data-zone-data="broken">Послезавтра, ПВЗ<script>доставка сегодня</script></div></div>'
        by_path, _ = extract_yandex_deliveries(html, reference_date=self.reference)
        self.assertEqual(by_path["/card/item/1"]["latest_date"], "2026-11-14")
        self.assertNotIn("сегодня", by_path["/card/item/1"]["text"])

    def test_selected_method_does_not_mix_another_methods_dates_or_cost(self):
        html = '<div data-auto="snippet-delivery-options"><div data-zone-name="deliveryVariant" data-zone-data=\'{"deliveryDateTo":"2026-11-14","priceValue":100,"priceCurrency":"RUB"}\'></div><div data-zone-name="deliveryVariant" data-zone-data=\'{"deliveryDateTo":"2026-11-17","priceValue":0,"priceCurrency":"RUR","selected":true}\'></div></div>'
        _, primary = extract_yandex_deliveries(html)
        self.assertEqual(primary["latest_date"], "2026-11-17")
        self.assertEqual(primary["cost"], 0)

    def test_relative_dates_are_anchored_at_fetch_time(self):
        for text, first, last in [("Сегодня", "2026-11-12", "2026-11-12"),
                                  ("Завтра", "2026-11-13", "2026-11-13"),
                                  ("Послезавтра, ПВЗ", "2026-11-14", "2026-11-14"),
                                  ("Сегодня‐завтра", "2026-11-12", "2026-11-13")]:
            with self.subTest(text=text):
                d = delivery_data(text, reference_date=self.reference)
                self.assertEqual((d["earliest_date"], d["latest_date"]), (first, last))
                self.assertEqual(d["observed_on"], "2026-11-12")

    def test_visible_date_ranges_and_earliest_only_dates(self):
        d = delivery_data("20 – 25 ноя, ПВЗ", reference_date=self.reference)
        self.assertEqual((d["earliest_date"], d["latest_date"]), ("2026-11-20", "2026-11-25"))
        d = delivery_data("С 15 ноября", reference_date=self.reference)
        self.assertEqual(d["earliest_date"], "2026-11-15")
        self.assertNotIn("latest_date", d)
        d = delivery_data("1–3 дня", reference_date=self.reference)
        self.assertEqual((d["min_days"], d["max_days"]), (1, 3))

    def test_partial_shipping_time_is_not_a_complete_estimate(self):
        d = schema_delivery({"shippingDetails": {"deliveryTime": {"transitTime": {"maxValue": 2, "unitCode": "DAY"}}}})
        self.assertTrue(d["partial"])
        self.assertNotIn("max_days", d)
        self.assertNotIn("latest_date", d)

    def test_explicit_dates_override_relative_text(self):
        d = delivery_data({"text":"Завтра", "earliest_date":"2026-11-20", "latest_date":"2026-11-25"}, reference_date=self.reference)
        self.assertEqual((d["earliest_date"], d["latest_date"]), ("2026-11-20", "2026-11-25"))

    def test_cross_month_range_keeps_the_last_day(self):
        d = delivery_data("30 ноября — 2 декабря", reference_date=self.reference)
        self.assertEqual((d["earliest_date"], d["latest_date"]), ("2026-11-30", "2026-12-02"))


if __name__ == "__main__":
    unittest.main()
