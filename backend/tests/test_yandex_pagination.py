import json
import unittest
from urllib.parse import parse_qs, urlparse

from src.parcers.ym import YandexMarketAdapter


def page_html(page):
    products = []
    for index in range(8):
        product_id = page * 100 + index
        products.append({
            "@type": "Product",
            "name": "Товар {}".format(product_id),
            "url": "https://market.yandex.ru/card/item-{}".format(product_id),
            "offers": {"price": 1000 + product_id, "priceCurrency": "RUB"},
        })
    return '<script type="application/ld+json">{}</script>'.format(
        json.dumps(products, ensure_ascii=False)
    )


class YandexSearchPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_public_search_pages_until_twenty_products(self):
        adapter = YandexMarketAdapter(
            marketplace="Яндекс Маркет",
            search_url="https://market.yandex.ru/search?text={query}",
            allowed_hosts=("market.yandex.ru",),
        )
        requested = []

        async def fetch(url):
            requested.append(url)
            page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
            return url, page_html(page)

        adapter._fetch_public_page = fetch
        result = await adapter.search("телефон", limit=20)

        self.assertEqual(len(result.offers), 20)
        self.assertEqual(len({offer.url for offer in result.offers}), 20)
        self.assertEqual(len(requested), 3)
        self.assertIn("page=2", requested[1])
        self.assertIn("page=3", requested[2])


if __name__ == "__main__":
    unittest.main()
