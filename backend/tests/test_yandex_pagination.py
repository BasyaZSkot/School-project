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


def search_card_html():
    cards = []
    for product_id, title, price in [
        (123456, "Кофемашина Philips 3300", "68 103 ₽"),
        (234567, "Кофемашина DeLonghi", "71 500 ₽"),
    ]:
        cards.append(
            '<div data-auto="searchOrganic">'
            '<a data-auto="snippet-link" href="/card/coffee-maker/{id}?source=search">'
            '<span data-auto="snippet-title">{title}</span></a>'
            '<span data-auto="snippet-price-current">{price}</span>'
            '<img src="https://avatars.mds.yandex.net/images/{id}.jpg">'
            '</div>'.format(id=product_id, title=title, price=price)
        )
    return "<html><body>{}</body></html>".format("".join(cards))


class YandexSearchPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_data_auto_search_cards_when_jsonld_is_missing(self):
        adapter = YandexMarketAdapter(
            marketplace="Яндекс Маркет",
            search_url="https://market.yandex.ru/search?text={query}",
            allowed_hosts=("market.yandex.ru",),
        )
        requested = []

        async def fetch(url):
            requested.append(url)
            return url, search_card_html()

        adapter._fetch_public_page = fetch
        result = await adapter.search("кофемашина", limit=2)

        self.assertEqual(result.status.value, "ready")
        self.assertEqual(len(result.offers), 2)
        self.assertEqual(result.offers[0].price, 68103)
        self.assertEqual(result.offers[0].external_id, "123456")
        self.assertEqual(result.offers[0].url, "https://market.yandex.ru/card/coffee-maker/123456")
        self.assertEqual(len(requested), 1)

    async def test_stops_on_challenge_and_keeps_first_page_cards(self):
        adapter = YandexMarketAdapter(
            marketplace="Яндекс Маркет",
            search_url="https://market.yandex.ru/search?text={query}",
            allowed_hosts=("market.yandex.ru",),
        )

        async def fetch(url):
            if "page=" in url:
                return "https://market.yandex.ru/showcaptcha", "<html>SmartCaptcha</html>"
            return url, search_card_html()

        adapter._fetch_public_page = fetch
        result = await adapter.search("кофемашина", limit=20)

        self.assertEqual(result.status.value, "ready")
        self.assertEqual(len(result.offers), 2)
        self.assertIn("проверку", result.message)
        self.assertTrue(result.has_more)

    async def test_fetches_beyond_five_pages_to_fill_larger_batches(self):
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
        result = await adapter.search("телефон", limit=61)

        self.assertEqual(len(result.offers), 61)
        self.assertEqual(len(requested), 8)
        self.assertIn("page=8", requested[-1])
        self.assertEqual(result.status.value, "ready")

    async def test_collects_up_to_two_hundred_products_from_public_pages(self):
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
        result = await adapter.search("телефон", limit=200)

        self.assertEqual(len(result.offers), 200)
        self.assertEqual(len({offer.url for offer in result.offers}), 200)
        self.assertEqual(len(requested), 25)
        self.assertIn("page=25", requested[-1])


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
