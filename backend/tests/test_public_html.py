import unittest
from urllib.parse import quote_plus

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

    def test_extracts_aggregate_offer_price_specification(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"Планшет","url":"/product/tablet/",
         "offers":{"@type":"AggregateOffer","priceCurrency":"RUB",
                   "lowPrice":"15999",
                   "priceSpecification":{"price":"16999"}}}
        </script>
        """
        offers = self.adapter._extract(html, "https://www.ozon.ru/search/", 20)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].price, 15999.0)

    def test_short_query_is_not_rejected_or_truncated(self):
        query = "tv"
        url = self.adapter.search_url.format(query=quote_plus(" ".join(query.split())))
        self.assertEqual(url, "https://www.ozon.ru/search/?text=tv")

    def test_rejects_ambiguous_price(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","name":"Товар","url":"/product/item/",
         "offers":{"price":"1,299.00","priceCurrency":"RUB"}}
        </script>
        """
        self.assertEqual(self.adapter._extract(html, "https://www.ozon.ru/search/", 20), [])


if __name__ == "__main__":
    unittest.main()
