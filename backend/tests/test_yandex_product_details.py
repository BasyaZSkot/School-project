import json
import unittest

from src.parcers.ym import YandexMarketAdapter


class YandexProductDetailsTests(unittest.TestCase):
    def setUp(self):
        self.adapter = YandexMarketAdapter(
            marketplace="Яндекс Маркет",
            search_url="https://market.yandex.ru/search?text={query}",
            allowed_hosts=("market.yandex.ru",),
        )

    @staticmethod
    def _product_row(name, value):
        return (
            '<div class="spec-row"><div><div><span data-auto="product-spec">'
            f"{name}</span></div></div><div><span>{value}</span></div></div>"
        )

    def test_extracts_product_spec_rows_from_public_html(self):
        html = (
            '<h1 data-auto="productCardTitle">Штатив Example</h1>'
            '<span data-auto="snippet-price-current">1 200 ₽</span>'
            '<div data-zone-name="ProductSpecsList">'
            + self._product_row("Материал", "Алюминий")
            + self._product_row("Максимальная высота", "160 см")
            + "</div>"
        )

        offer = self.adapter._extract_product(
            html, "https://market.yandex.ru/card/tripod/123456"
        )

        self.assertIsNotNone(offer)
        self.assertEqual(offer.specifications, [
            {"name": "Материал", "value": "Алюминий"},
            {"name": "Максимальная высота", "value": "160 см"},
        ])

    def test_merges_public_markup_specs_with_jsonld_specs(self):
        jsonld = {
            "@type": "Product",
            "name": "Штатив Example",
            "url": "https://market.yandex.ru/card/tripod/123456",
            "description": "Лёгкий штатив для камеры.",
            "additionalProperty": [
                {"name": "Материал", "value": "Алюминий"},
                {"name": "Совместимость", "value": "Камеры"},
            ],
            "offers": {"price": "1200", "priceCurrency": "RUB"},
        }
        html = (
            '<h1 data-auto="productCardTitle">Штатив Example</h1>'
            '<span data-auto="snippet-price-current">1 200 ₽</span>'
            '<div data-zone-name="ProductSpecsList">'
            + self._product_row("Материал", "Алюминий")
            + "</div>"
            + '<script type="application/ld+json">'
            + json.dumps(jsonld, ensure_ascii=False)
            + "</script>"
        )

        offer = self.adapter._extract_product(
            html, "https://market.yandex.ru/card/tripod/123456"
        )

        self.assertIsNotNone(offer)
        self.assertEqual(offer.description, "Лёгкий штатив для камеры.")
        self.assertEqual(offer.specifications, [
            {"name": "Материал", "value": "Алюминий"},
            {"name": "Совместимость", "value": "Камеры"},
        ])

    def test_keeps_markup_specs_when_jsonld_provides_product_basics(self):
        jsonld = {
            "@type": "Product",
            "name": "Штатив Example",
            "url": "https://market.yandex.ru/card/tripod/123456",
            "offers": {"price": "1200", "priceCurrency": "RUB"},
        }
        html = (
            '<div data-zone-name="ProductSpecsList">'
            + self._product_row("Материал", "Алюминий")
            + "</div>"
            + '<script type="application/ld+json">'
            + json.dumps(jsonld, ensure_ascii=False)
            + "</script>"
        )

        offer = self.adapter._extract_product(
            html, "https://market.yandex.ru/card/tripod/123456"
        )

        self.assertIsNotNone(offer)
        self.assertEqual(offer.specifications, [
            {"name": "Материал", "value": "Алюминий"},
        ])


if __name__ == "__main__":
    unittest.main()
