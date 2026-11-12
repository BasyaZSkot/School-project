import asyncio
from unittest.mock import AsyncMock, patch
import unittest

from fastapi.testclient import TestClient
from src.parcers.api import app
from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.regions import REGIONS, current_region, get_region, regional_delivery, regional_url, region_scope
from src.parcers.service import MarketplaceSearchService
from src.parcers import transport
from src.parcers.yandex_delivery import extract_yandex_deliveries


class RegionTests(unittest.TestCase):
    def test_catalog_is_unique_and_region_ids_are_validated(self):
        self.assertEqual(len({r["id"] for r in REGIONS}), len(REGIONS))
        self.assertEqual(get_region(213)["name"], "Москва")
        with self.assertRaises(ValueError): get_region(999999)
        with self.assertRaises(ValueError): get_region(True)

    def test_scope_and_urls_do_not_leak_to_another_request(self):
        with region_scope(213):
            self.assertIn("lr=213", regional_url("https://market.yandex.ru/search?text=a&lr=2&page=3"))
            self.assertNotIn("lr=2&", regional_url("https://market.yandex.ru/search?lr=2&page=3"))
            self.assertEqual(regional_url("https://www.ozon.ru/product/a"), "https://www.ozon.ru/product/a")
        self.assertIsNone(current_region())
        self.assertNotIn("lr", regional_url("https://market.yandex.ru/search?text=a"))

    def test_wrong_city_dates_and_cost_are_not_relabelled(self):
        delivery = {"region_id":2,"destination":"Санкт-Петербург","latest_date":"2026-11-14","cost":0,"currency":"RUB"}
        with region_scope(213):
            result = regional_delivery(delivery)
        self.assertFalse(result["region_confirmed"])
        self.assertNotIn("latest_date", result)
        self.assertNotIn("cost", result)
        self.assertEqual(result["source_destination"], "Санкт-Петербург")
        self.assertIn("latest_date", delivery)
        with region_scope(2):
            self.assertTrue(regional_delivery(delivery)["region_confirmed"])

    def test_region_marker_is_read_from_the_public_delivery_point(self):
        html = '<div data-zone-name="deliveryPoint" data-zone-data=\'{"regionId":213}\'>Москва</div><div data-auto="snippet-delivery-options"><div data-zone-name="deliveryVariant" data-zone-data=\'{"deliveryDateTo":"2026-11-14"}\'></div></div>'
        _, delivery = extract_yandex_deliveries(html)
        self.assertEqual(delivery["region_id"], 213)

    def test_anonymous_sessions_and_response_caches_are_separate_by_region(self):
        with patch.object(transport, "_regional_shared", {}):
            with region_scope(213): first = transport.get_shared_fetcher()
            with region_scope(2): second = transport.get_shared_fetcher()
            with region_scope(213): self.assertIs(transport.get_shared_fetcher(), first)
            self.assertIsNot(first, second)

    def test_regions_endpoint_and_search_forwarding(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        self.assertEqual(client.get("/api/regions").json()["regions"], REGIONS)
        with patch("src.parcers.api.search_service.search", new_callable=AsyncMock) as search:
            search.return_value = {"products":[],"providers":[]}
            self.assertEqual(client.get("/api/search",params={"q":"phone","region_id":213}).status_code,200)
            search.assert_awaited_once_with("phone",20,0,session_id=None,region_id=213)
            search.reset_mock()
            self.assertEqual(client.get("/api/search",params={"q":"phone","region_id":999999}).status_code,400)
            search.assert_not_awaited()

    def test_product_details_validate_and_forward_region(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        with patch("src.parcers.api.search_service.parse_product", new_callable=AsyncMock) as parser:
            parser.return_value = None
            url = "https://market.yandex.ru/card/item/123"
            self.assertEqual(client.get("/api/product-details",params={"marketplace":"Яндекс Маркет","product_url":url,"region_id":2}).status_code,200)
            parser.assert_awaited_once_with("Яндекс Маркет",url,region_id=2)
            parser.reset_mock()
            self.assertEqual(client.get("/api/product-details",params={"marketplace":"Яндекс Маркет","product_url":url,"region_id":999999}).status_code,422)
            parser.assert_not_awaited()


class RegionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_regions_keep_distinct_context_and_search_sessions(self):
        class Adapter:
            marketplace = "Яндекс Маркет"
            async def search(self, query, limit):
                await asyncio.sleep(0)
                city = current_region()
                offer = Offer(marketplace=self.marketplace,title="Товар",price=100,currency="RUB",url="https://market.yandex.ru/card/item/123",delivery={"region_id":city["id"],"destination":city["name"],"max_days":2})
                return ProviderResult(self.marketplace,SearchStatus.READY,"https://market.yandex.ru/search?text=a",[offer])
        service = MarketplaceSearchService(adapters=[Adapter()])
        a,b = await asyncio.gather(service.search("phone",session_id="same-session",region_id=213),service.search("phone",session_id="same-session",region_id=2))
        self.assertEqual(a["products"][0]["offers"][0]["delivery"]["region_id"],213)
        self.assertEqual(b["products"][0]["offers"][0]["delivery"]["region_id"],2)
        self.assertEqual(len(service._search_sessions),2)
        self.assertIsNone(current_region())

    async def test_unconfirmed_provider_is_reported_without_wrong_city_estimate(self):
        class Adapter:
            marketplace = "Яндекс Маркет"
            async def search(self, query, limit):
                offer = Offer(marketplace=self.marketplace,title="Товар",price=100,currency="RUB",url="https://market.yandex.ru/card/item/123",delivery={"region_id":2,"destination":"Санкт-Петербург","max_days":2})
                return ProviderResult(self.marketplace,SearchStatus.READY,"https://market.yandex.ru/search?text=a",[offer])
        response = await MarketplaceSearchService(adapters=[Adapter()]).search("phone",region_id=213)
        self.assertIn("не подтвердила",response["notice"])
        self.assertFalse(response["products"][0]["offers"][0]["delivery"]["region_confirmed"])


if __name__ == "__main__": unittest.main()
