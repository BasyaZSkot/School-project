import asyncio
import unittest
from unittest.mock import patch

import httpx

from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.service import MarketplaceSearchService


class FakeAdapter:
    search_url = "https://example.org/search?q={query}"
    def __init__(self, marketplace, offers=None, delay=0, fail=False):
        self.marketplace = marketplace
        self.offers = offers or []
        self.delay = delay
        self.fail = fail

    async def search(self, query, limit=20):
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("test failure")
        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY,
            search_url="https://example.org/search",
            offers=self.offers[:limit],
        )


def make_offer(marketplace, title, price, currency="RUB", gtin="4601234567890", item_id="1"):
    return Offer(
        marketplace=marketplace,
        title=title,
        price=price,
        currency=currency,
        url=f"https://example.org/{marketplace}/{item_id}",
        external_id=item_id,
        gtin=gtin,
    )


class SearchMarketplaceSelectionTests(unittest.IsolatedAsyncioTestCase):
    def test_default_configuration_searches_only_yandex(self):
        with patch("src.parcers.service.os.getenv", side_effect=lambda _name, default=None: default):
            service = MarketplaceSearchService()

        self.assertEqual(service.enabled_search_marketplaces, {"Яндекс Маркет"})
        self.assertEqual(
            [adapter.marketplace for adapter in service.search_adapters],
            ["Ozon", "Wildberries", "Яндекс Маркет"],
        )
        self.assertEqual(service.search_adapters[0].status.value, "disabled")
        self.assertEqual(service.search_adapters[1].status.value, "disabled")

    async def test_disabled_marketplaces_are_reported_without_network_searches(self):
        class CountingAdapter(FakeAdapter):
            def __init__(self, marketplace, offers=None):
                super().__init__(marketplace, offers)
                self.search_calls = 0

            async def search(self, query, limit=20):
                self.search_calls += 1
                return await super().search(query, limit)

        ozon = CountingAdapter("Ozon", [make_offer("Ozon", "Ozon item", 100, item_id="oz")])
        wb = CountingAdapter("Wildberries", [make_offer("Wildberries", "WB item", 110, item_id="wb")])
        yandex = CountingAdapter("Яндекс Маркет", [make_offer("Яндекс Маркет", "Yandex item", 90, item_id="ym")])
        service = MarketplaceSearchService(
            adapters=[ozon, wb, yandex],
            enabled_search_marketplaces={"Яндекс Маркет"},
        )

        result = await service.search("item")
        providers = {provider["marketplace"]: provider for provider in result["providers"]}

        self.assertEqual((ozon.search_calls, wb.search_calls, yandex.search_calls), (0, 0, 1))
        self.assertEqual(providers["Ozon"]["status"], "disabled")
        self.assertEqual(providers["Wildberries"]["status"], "disabled")
        self.assertEqual(providers["Яндекс Маркет"]["status"], "ready")
        self.assertEqual(len(result["products"]), 1)
        self.assertIn("https://example.org/search", providers["Ozon"]["search_url"])


class MarketplaceSearchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_groups_same_gtin_and_sorts_within_currency(self):
        adapters = [
            FakeAdapter("WB", [make_offer("WB", "Headphones", 3000, item_id="1")]),
            FakeAdapter("Ozon", [make_offer("Ozon", "Headphones model", 2500, item_id="2")]),
        ]
        result = await MarketplaceSearchService(adapters).search(" headphones ")

        self.assertEqual(result["query"], "headphones")
        self.assertEqual(result["total_offers"], 2)
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["lowest_price_by_currency"], {"RUB": 2500.0})
        self.assertEqual(result["products"][0]["offers"][0]["marketplace"], "Ozon")

    async def test_keeps_same_marketplace_listings_in_separate_products(self):
        adapters = [
            FakeAdapter("Яндекс Маркет", [
                make_offer("Яндекс Маркет", "Coffee maker X", 10000, item_id="ym-1"),
                make_offer("Яндекс Маркет", "Coffee maker X", 10500, item_id="ym-2"),
            ]),
        ]
        result = await MarketplaceSearchService(adapters).search("кофемашина")

        self.assertEqual(result["total_offers"], 2)
        self.assertEqual(len(result["products"]), 2)
        self.assertTrue(all(len(product["offers"]) == 1 for product in result["products"]))

    async def test_cross_marketplace_matches_one_offer_per_marketplace(self):
        adapters = [
            FakeAdapter("Ozon", [make_offer("Ozon", "Coffee maker X", 10000, item_id="oz-1")]),
            FakeAdapter("Яндекс Маркет", [
                make_offer("Яндекс Маркет", "Coffee maker X", 9900, item_id="ym-1"),
                make_offer("Яндекс Маркет", "Coffee maker X", 10500, item_id="ym-2"),
            ]),
        ]
        result = await MarketplaceSearchService(adapters).search("кофемашина")

        self.assertEqual(len(result["products"]), 2)
        self.assertCountEqual(
            sorted(len(product["offers"]) for product in result["products"]),
            [1, 2],
        )
        self.assertTrue(all(
            len({offer["marketplace"] for offer in product["offers"]}) == len(product["offers"])
            for product in result["products"]
        ))

    async def test_does_not_compare_different_currencies(self):
        adapters = [
            FakeAdapter("A", [make_offer("A", "Same item", 100, "USD", item_id="a")]),
            FakeAdapter("B", [make_offer("B", "Same item", 200, "RUB", item_id="b")]),
        ]
        result = await MarketplaceSearchService(adapters).search("item")
        self.assertEqual(result["products"][0]["lowest_price_by_currency"], {"RUB": 200.0, "USD": 100.0})

    async def test_provider_failure_does_not_fail_whole_search(self):
        result = await MarketplaceSearchService([
            FakeAdapter("Broken", fail=True),
            FakeAdapter("Healthy", [make_offer("Healthy", "Item", 10)]),
        ]).search("item")
        self.assertEqual(result["providers"][0]["status"], "error")
        self.assertEqual(result["total_offers"], 1)

    async def test_provider_timeout_is_reported(self):
        result = await MarketplaceSearchService(
            [FakeAdapter("Slow", delay=0.2)],
            provider_timeout=0.01,
        ).search("item")
        self.assertEqual(result["providers"][0]["status"], "error")
        self.assertIn("timeout", result["providers"][0]["message"])

    async def test_access_restriction_is_reported_without_retrying(self):
        request = httpx.Request("GET", "https://www.wildberries.ru/search")
        response = httpx.Response(498, request=request)
        error = httpx.HTTPStatusError("blocked", request=request, response=response)

        class RestrictedAdapter(FakeAdapter):
            async def search(self, query, limit=20):
                raise error

        result = await MarketplaceSearchService([RestrictedAdapter("Wildberries")]).search("tv")
        self.assertEqual(result["providers"][0]["status"], "policy_restricted")
        self.assertIn("498", result["providers"][0]["message"])
        self.assertIn("https://", result["providers"][0]["search_url"])

    async def test_rejects_empty_query_and_invalid_limit(self):
        service = MarketplaceSearchService([])
        with self.assertRaises(ValueError):
            await service.search("  ")
        with self.assertRaises(ValueError):
            await service.search("item", 0)


if __name__ == "__main__":
    unittest.main()
