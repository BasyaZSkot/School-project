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
            asyncio.run(service.search("phone", limit=20, offset=101))


if __name__ == "__main__":
    unittest.main()
