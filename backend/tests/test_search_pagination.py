import asyncio
import unittest

from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.service import MarketplaceSearchService


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
        with self.assertRaises(ValueError):
            asyncio.run(service.search("phone", limit=20, offset=151))


class MergingAdapter:
    """Endless catalogue where every second card duplicates the previous title."""

    marketplace = "Yandex Market"

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        offers = []
        for index in range(min(100, limit)):
            title_index = index - 1 if index == 1 else index
            offers.append(
                Offer(
                    marketplace=self.marketplace,
                    title=f"item {title_index:03d}",
                    price=100 + index,
                    currency="RUB",
                    url=f"https://market.example/items/{index}",
                    external_id=f"ym-{index}",
                )
            )
        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY,
            search_url="https://example.com/search",
            offers=offers,
        )


class MergedProductsKeepPaginationTests(unittest.TestCase):
    def test_load_more_stays_available_when_grouping_merges_two_offers(self):
        service = MarketplaceSearchService(adapters=[MergingAdapter()])
        first = asyncio.run(service.search("phone", limit=20, offset=0))
        # 21 offers were fetched, two of them merged -> exactly 20 products,
        # but the provider filled its quota, so more cards exist.
        self.assertEqual(len(first["products"]), 20)
        self.assertEqual(first["total_products"], 20)
        self.assertTrue(first["has_more"])

        second = asyncio.run(service.search("phone", limit=20, offset=20))
        self.assertEqual(len(second["products"]), 20)
        self.assertTrue(second["has_more"])

    def test_no_more_after_the_hard_provider_cap(self):
        service = MarketplaceSearchService(adapters=[MergingAdapter()])
        last = asyncio.run(service.search("phone", limit=20, offset=40))
        self.assertFalse(last["has_more"])

    def test_no_more_when_provider_returned_less_than_requested(self):
        service = MarketplaceSearchService(adapters=[FakeAdapter("Ozon", "ozon", 5)])
        result = asyncio.run(service.search("phone", limit=20, offset=0))
        self.assertFalse(result["has_more"])


if __name__ == "__main__":
    unittest.main()
