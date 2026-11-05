import unittest

from src.parcers.public_html import PublicHtmlSearchAdapter


class PublicMarketplaceHtmlTests(unittest.TestCase):
    def setUp(self):
        self.adapter = PublicHtmlSearchAdapter(
            marketplace="Ozon",
            search_url="https://www.ozon.ru/search/?text={query}",
            allowed_hosts=("ozon.ru",),
        )

    def test_extracts_product_jsonld(self):
        html = """
        <html><script type="application/ld+json">
        {"@type":"Product","name":"Наушники Example","sku":"sku-1",
         "url":"https://www.ozon.ru/product/example-1/",
         "image":"https://cdn.ozon.ru/image.webp",
         "brand":{"@type":"Brand","name":"Example"},
         "offers":{"@type":"Offer","price":"12990","priceCurrency":"RUB",
                   "availability":"https://schema.org/InStock"}}
        </script></html>
        """
        offers = self.adapter._extract(html, "https://www.ozon.ru/search/?text=headphones", 20)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].title, "Наушники Example")
        self.assertEqual(offers[0].price, 12990.0)
        self.assertEqual(offers[0].brand, "Example")
        self.assertTrue(offers[0].in_stock)

    def test_ignores_product_urls_outside_marketplace(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"External","url":"https://evil.example/item",
         "offers":{"price":"10","priceCurrency":"RUB"}}
        </script>
        """
        self.assertEqual(self.adapter._extract(html, "https://www.ozon.ru/search/", 20), [])

    def test_handles_itemlist_wrapped_product(self):
        html = """
        <script type="application/ld+json">
        {"@type":"ItemList","itemListElement":[{"@type":"ListItem","item":{
          "@type":"Product","name":"Кофемашина","url":"/product/coffee/",
          "offers":{"price":5000,"priceCurrency":"RUB"}}}]}
        </script>
        """
        offers = self.adapter._extract(html, "https://www.ozon.ru/search/", 20)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].url, "https://www.ozon.ru/product/coffee/")


if __name__ == "__main__":
    unittest.main()
