import asyncio
import unittest

from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.service import PROVIDER_FETCH_CAP, MarketplaceSearchService


class FakeAdapter:
    def __init__(self, marketplace: str, prefix: str, count: int):
        self.marketplace = marketplace
        self.prefix = prefix
        self.count = count

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        offers = [
            Offer(
                marketplace=self.marketplace,
                title=f"{self.prefix} product {index:02d}",
                price=100 + index,
                currency="RUB",
                url=f"https://{self.marketplace.lower()}.example/items/{index}",
                external_id=f"{self.prefix}-{index}",
            )
            for index in range(min(self.count, limit))
        ]
        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY if offers else SearchStatus.NO_RESULTS,
            search_url="https://example.com/search",
            offers=offers,
        )


class SearchPaginationTests(unittest.TestCase):
    def test_returns_twenty_products_then_next_page_without_overlap(self):
        service = MarketplaceSearchService(
            adapters=[
                FakeAdapter("Ozon", "ozon", 15),
                FakeAdapter("Wildberries", "wb", 15),
            ]
        )

        first = asyncio.run(service.search("phone", limit=20, offset=0))
        second = asyncio.run(service.search("phone", limit=20, offset=20))

        first_keys = {item["match_key"] for item in first["products"]}
        second_keys = {item["match_key"] for item in second["products"]}
        self.assertEqual(len(first["products"]), 20)
        self.assertEqual(len(second["products"]), 10)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertFalse(first_keys.intersection(second_keys))
        self.assertEqual(first["total_products"], 30)
        self.assertEqual(second["total_products"], 30)

    def test_rejects_offset_above_supported_range(self):
        service = MarketplaceSearchService(adapters=[])
        max_offset = PROVIDER_FETCH_CAP * 3
        asyncio.run(service.search("phone", limit=20, offset=max_offset))  # still allowed
        with self.assertRaises(ValueError):
            asyncio.run(service.search("phone", limit=20, offset=max_offset + 1))


class MergingAdapter:
    """Same catalog exposed by each marketplace, merged across marketplaces."""

    def __init__(self, marketplace: str):
        self.marketplace = marketplace

    supply = 100_000

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        offers = [
            Offer(
                marketplace=self.marketplace,
                title=f"item {index:03d}",
                price=100 + index,
                currency="RUB",
                url=f"https://{self.marketplace.lower()}.example/items/{index}",
                external_id=f"{self.marketplace}-{index}",
            )
            for index in range(min(self.supply, limit))
        ]
        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY,
            search_url="https://example.com/search",
            offers=offers,
        )


class SameTitleAdapter:
    marketplace = "Ozon"

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY,
            search_url="https://example.com/search",
            offers=[
                Offer(
                    marketplace=self.marketplace,
                    title="Одинаковое название товара",
                    price=100 + index,
                    currency="RUB",
                    url=f"https://ozon.example/items/{index}",
                    external_id=f"ozon-{index}",
                )
                for index in range(min(80, limit))
            ],
        )


class MergedProductsKeepPaginationTests(unittest.TestCase):
    def test_load_more_stays_available_when_grouping_merges_two_offers(self):
        service = MarketplaceSearchService(adapters=[
            MergingAdapter("Ozon"), MergingAdapter("Wildberries"),
        ])
        first = asyncio.run(service.search("phone", limit=20, offset=0))
        # The providers return matching products; their offers merge into
        # cross-marketplace cards, while the provider still has more products.
        self.assertEqual(len(first["products"]), 20)
        self.assertEqual(first["total_products"], 21)
        self.assertEqual(len(first["products"][0]["offers"]), 2)
        self.assertTrue(first["has_more"])

        second = asyncio.run(service.search("phone", limit=20, offset=20))
        self.assertEqual(len(second["products"]), 20)
        self.assertTrue(second["has_more"])

    def test_no_more_once_the_fetch_cap_is_exhausted(self):
        adapter = MergingAdapter("Ozon")
        adapter.supply = PROVIDER_FETCH_CAP  # exactly the ceiling, nothing beyond it
        service = MarketplaceSearchService(adapters=[adapter])
        last_offset = (PROVIDER_FETCH_CAP // 20 - 1) * 20
        last = asyncio.run(service.search("phone", limit=20, offset=last_offset))
        self.assertFalse(last["has_more"])

    def test_no_more_when_provider_returned_less_than_requested(self):
        service = MarketplaceSearchService(adapters=[FakeAdapter("Ozon", "ozon", 5)])
        result = asyncio.run(service.search("phone", limit=20, offset=0))
        self.assertFalse(result["has_more"])


class SameMarketplaceListingsPaginationTests(unittest.TestCase):
    def test_second_and_third_load_more_return_new_same_title_products(self):
        service = MarketplaceSearchService(adapters=[SameTitleAdapter()])
        pages = [
            asyncio.run(service.search("item", limit=20, offset=offset))
            for offset in (0, 20, 40, 60)
        ]
        ids = [[product["offers"][0]["external_id"] for product in page["products"]]
               for page in pages]
        self.assertEqual([len(page["products"]) for page in pages], [20, 20, 20, 20])
        self.assertTrue(all(page["has_more"] for page in pages[:3]))
        self.assertFalse(pages[3]["has_more"])
        self.assertEqual(len(set(sum(ids, []))), 80)


class SearchSessionKeepsResultsOnProviderFailureTests(unittest.TestCase):
    def test_cached_prefix_survives_temporary_failure_and_allows_retry(self):
        class IntermittentAdapter:
            marketplace = "Yandex Market"
            fail = False

            async def search(self, query: str, limit: int = 20) -> ProviderResult:
                if self.fail:
                    raise RuntimeError("temporary marketplace failure")
                offers = [
                    Offer(
                        marketplace=self.marketplace,
                        title=f"cached item {index:03d}",
                        price=100 + index,
                        currency="RUB",
                        url=f"https://market.example/items/{index}",
                        external_id=f"item-{index}",
                    )
                    for index in range(min(70, limit))
                ]
                return ProviderResult(
                    marketplace=self.marketplace,
                    status=SearchStatus.READY,
                    search_url="https://market.example/search",
                    offers=offers,
                )

        adapter = IntermittentAdapter()
        service = MarketplaceSearchService(adapters=[adapter])
        session_id = "session-test-123"
        first = asyncio.run(service.search("item", limit=20, offset=0, session_id=session_id))
        second = asyncio.run(service.search("item", limit=20, offset=20, session_id=session_id))
        self.assertEqual(len(first["products"]), 20)
        self.assertEqual(len(second["products"]), 20)

        adapter.fail = True
        third = asyncio.run(service.search("item", limit=20, offset=40, session_id=session_id))
        self.assertEqual(len(third["products"]), 1)
        self.assertEqual(third["products"][0]["offers"][0]["external_id"], "item-40")
        self.assertTrue(third["has_more"])

        retry = asyncio.run(service.search("item", limit=20, offset=41, session_id=session_id))
        self.assertEqual(retry["products"], [])
        self.assertTrue(retry["retryable"])
        self.assertTrue(retry["has_more"])

        adapter.fail = False
        recovered = asyncio.run(service.search("item", limit=20, offset=41, session_id=session_id))
        self.assertEqual(len(recovered["products"]), 20)
        self.assertFalse(recovered["retryable"])


class StillHasMoreFarBeyondOldCapTests(unittest.TestCase):
    """Regression test: the "show more" button used to disappear after just
    one or two clicks, as soon as provider_limit reached the old 50-item cap
    -- even when a provider clearly had many more items to give. It must now
    stay available for as many clicks as the provider can actually support,
    up to the new, much larger PROVIDER_FETCH_CAP.
    """

    def test_load_more_survives_many_clicks(self):
        service = MarketplaceSearchService(adapters=[
            MergingAdapter("Ozon"), MergingAdapter("Wildberries"),
        ])
        offset = 0
        clicks = 0
        while True:
            result = asyncio.run(service.search("phone", limit=20, offset=offset))
            self.assertGreater(len(result["products"]), 0)
            if not result["has_more"]:
                break
            offset += 20
            clicks += 1
            self.assertLess(clicks, 20, "has_more should have become False by now")
        # The button should survive well past offset=40, where the old
        # 50-item cap used to kill it after just two clicks.
        self.assertGreaterEqual(offset, 160)


class PublicHtmlProviderPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_html_adapter_keeps_pages_working_after_offset_50(self):
        import json

        from src.parcers.public_html import PublicHtmlSearchAdapter
        from src.parcers.transport import FetchedPage

        records = [{
            "@type": "Product",
            "name": f"Test item {index:03d}",
            "sku": str(index),
            "url": f"https://www.ozon.ru/product/item-{index}/",
            "offers": {"price": str(100 + index), "priceCurrency": "RUB"},
        } for index in range(70)]
        html = '<script type="application/ld+json">' + json.dumps({"@graph": records}) + '</script>'

        class StaticFetcher:
            async def fetch(self, url):
                return FetchedPage(url=url, text=html, status_code=200)

        adapter = PublicHtmlSearchAdapter(
            marketplace="Ozon",
            search_url="https://www.ozon.ru/search/?text={query}",
            allowed_hosts=("ozon.ru",),
            fetcher=StaticFetcher(),
        )
        service = MarketplaceSearchService(adapters=[adapter])
        session_id = "large-page-session"
        pages = [
            await service.search("item", limit=20, offset=offset, session_id=session_id)
            for offset in (0, 20, 40, 60)
        ]

        self.assertEqual([len(page["products"]) for page in pages], [20, 20, 20, 10])
        self.assertTrue(all(page["has_more"] for page in pages[:3]))
        self.assertFalse(pages[3]["has_more"])
        self.assertEqual(
            [page["products"][0]["offers"][0]["external_id"] for page in pages],
            ["0", "20", "40", "60"],
        )

if __name__ == "__main__":
    unittest.main()
