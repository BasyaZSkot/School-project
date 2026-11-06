import json
import unittest

from src.parcers.embedded_state import (
    embedded_json_documents,
    extract_ozon_embedded,
    extract_wildberries_embedded,
)
from src.parcers.wb import WildberriesAdapter
from src.parcers.ozon import OzonAdapter


class EmbeddedMarketplaceSearchStateTests(unittest.TestCase):
    def test_reads_wildberries_products_from_json_in_public_html(self):
        state = {
            "products": [{
                "id": 123456,
                "name": "Клавиатура Example",
                "brand": "Example",
                "sizes": [{"price": {"product": 129900, "basic": 149900}}],
                "totalQuantity": 7,
                "image_links": "https://basket-01.wbbasket.ru/photo.webp",
            }]
        }
        html = (
            '<html><script type="application/json" id="initial-state">'
            + json.dumps(state, ensure_ascii=False)
            + "</script></html>"
        )

        offers = extract_wildberries_embedded(html, 10)

        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].marketplace, "Wildberries")
        self.assertEqual(offers[0].title, "Клавиатура Example")
        self.assertEqual(offers[0].price, 1299.0)
        self.assertEqual(offers[0].url, "https://www.wildberries.ru/catalog/123456/detail.aspx")
        self.assertTrue(offers[0].in_stock)
        self.assertEqual(offers[0].image_url, "https://basket-01.wbbasket.ru/photo.webp")

    def test_reads_ozon_widget_states_already_embedded_in_html(self):
        widget = {
            "items": [{
                "sku": "ozon-777",
                "action": {"link": "/product/headphones-777/"},
                "mainState": [
                    {"id": "name", "textDS": {"text": "Наушники Example"}},
                    {"type": "priceV2", "priceV2": {"price": [{"text": "4 590 ₽", "textStyle": "PRICE"}]}},
                    {"gallery": [{"src": "https://cdn1.ozon.ru/s3/headphones.jpg"}]},
                ],
            }]
        }
        state = {"widgetStates": {"tileGridDesktop-1": json.dumps(widget, ensure_ascii=False)}}
        html = (
            '<html><script type="application/json" id="app-state">'
            + json.dumps(state, ensure_ascii=False)
            + "</script></html>"
        )
        adapter = OzonAdapter.from_env()

        offers = adapter._extract(html, "https://www.ozon.ru/search/?text=headphones", 10)

        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].marketplace, "Ozon")
        self.assertEqual(offers[0].title, "Наушники Example")
        self.assertEqual(offers[0].price, 4590.0)
        self.assertEqual(offers[0].url, "https://www.ozon.ru/product/headphones-777/")
        self.assertEqual(offers[0].external_id, "ozon-777")
        self.assertEqual(offers[0].image_url, "https://cdn1.ozon.ru/s3/headphones.jpg")

    def test_rejects_ozon_product_link_to_external_host(self):
        widget = {
            "items": [{
                "sku": "external",
                "action": {"link": "https://outside.example/item"},
                "mainState": [
                    {"id": "name", "textDS": {"text": "Чужой товар"}},
                    {"type": "priceV2", "priceV2": {"price": [{"text": "100 ₽", "textStyle": "PRICE"}]}},
                ],
            }]
        }
        state = {"widgetStates": {"tileGridDesktop-1": json.dumps(widget)}}
        html = (
            '<script type="application/json">'
            + json.dumps(state)
            + "</script>"
        )

        offers = extract_ozon_embedded(
            html,
            "https://www.ozon.ru/search/",
            OzonAdapter.from_env()._valid_marketplace_url,
        )

        self.assertEqual(offers, [])

    def test_ignores_non_json_scripts(self):
        html = '<script>window.state = {"products":[{"id":1}]};</script>'
        self.assertEqual(embedded_json_documents(html), [])


if __name__ == "__main__":
    unittest.main()
