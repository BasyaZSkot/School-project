import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from src.parcers.api import app
from src.parcers.pickup import PickupService, normalize_points


def feature(name="Яндекс Маркет", **changes):
    properties = {"name": name, "osm_key": "shop", "osm_value": "outpost", "osm_type": "N", "osm_id": 123,
                  "countrycode": "RU", "city": "Москва", "street": "Тверская улица", "housenumber": "7"}
    properties.update(changes)
    return {"properties": properties, "geometry": {"type": "Point", "coordinates": [37.62, 55.75]}}


class PickupNormalizationTests(unittest.TestCase):
    def normalize(self, features):
        return normalize_points(features, "Яндекс Маркет", {"id": 213}, (55.75, 37.62), 4)

    def test_only_actual_pickup_features_of_requested_brand_are_shown(self):
        self.assertEqual(len(self.normalize([feature(), feature("Ozon"), feature("Яндекс Маркет", osm_key="office", osm_value="company")])) , 1)

    def test_duplicate_and_outside_radius_points_are_removed(self):
        outside = feature(osm_id=4);outside["geometry"]["coordinates"] = [30, 60]
        points = self.normalize([feature(), feature(), outside])
        self.assertEqual([p["id"] for p in points], ["osm:N:123"])

    def test_missing_house_is_not_invented_and_point_is_flagged(self):
        point = self.normalize([feature(housenumber=None)])[0]
        self.assertFalse(point["address_complete"])
        self.assertEqual(point["address"], "Тверская улица, Москва")

    def test_bad_positions_and_country_are_ignored(self):
        a=feature();a["geometry"]["coordinates"]=[float("nan"),55]
        self.assertEqual(self.normalize([a, feature(countrycode="DE"), {"geometry":[]}, feature(osm_id=True)]), [])

    def test_lockers_and_brand_spelling_variants_are_supported(self):
        point = self.normalize([feature("Яндекс.Маркет", osm_key="amenity", osm_value="parcel_locker")])[0]
        self.assertEqual(point["kind"], "Постамат")
        self.assertEqual(point["source_url"], "https://www.openstreetmap.org/node/123")


class PickupServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_are_cached_but_markets_and_areas_stay_separate(self):
        service=PickupService()
        with patch.object(service,"city",AsyncMock(return_value=({"id":213,"name":"Москва"},(55.75,37.62)))), patch.object(service,"_json",AsyncMock(return_value=[feature()])) as fetch:
            first=await service.points(213,"Яндекс Маркет")
            await service.points(213,"Яндекс Маркет")
            second=await service.points(213,"Ozon")
            await service.points(213,"Яндекс Маркет",55.76,37.62)
            self.assertEqual(fetch.await_count,3)
            self.assertEqual(len(first["points"]),1)
            self.assertEqual(second["points"],[])

    async def test_cancelled_request_does_not_cancel_another_waiter_or_poison_cache(self):
        service=PickupService();started=asyncio.Event();finish=asyncio.Event()
        async def fetch(params):started.set();await finish.wait();return [feature()]
        with patch.object(service,"_json",fetch):
            first=asyncio.create_task(service._cached("same",{},60));await started.wait()
            second=asyncio.create_task(service._cached("same",{},60));first.cancel()
            with self.assertRaises(asyncio.CancelledError):await first
            finish.set();self.assertEqual(await second,[feature()])
            self.assertEqual(await service._cached("same",{},60),[feature()])

    async def test_city_lookup_requests_a_city_instead_of_state_centroid(self):
        service=PickupService()
        with patch.object(service,"_json",AsyncMock(return_value=[feature("Москва")])) as fetch:
            await service.city(213)
            self.assertEqual(fetch.call_args.args[0]["layer"],"city")
            self.assertNotIn("lang",fetch.call_args.args[0])

    async def test_address_results_are_deduplicated_and_scoped_to_city(self):
        service=PickupService();far=feature();far["geometry"]["coordinates"]=[30,60]
        with patch.object(service,"city",AsyncMock(return_value=({"id":213,"name":"Москва"},(55.75,37.62)))),patch.object(service,"_json",AsyncMock(return_value=[feature(),feature(),far])):
            results=await service.suggest(213,"Тверская 7")
            self.assertEqual(len(results["suggestions"]),1)
            self.assertEqual(results["suggestions"][0]["label"],"Тверская улица 7, Москва")

    async def test_invalid_area_does_not_request_points(self):
        service=PickupService()
        with patch.object(service,"city",AsyncMock(return_value=({"id":213,"name":"Москва"},(55.75,37.62)))),patch.object(service,"_json",AsyncMock()) as fetch:
            for lat,lon in [(55,None),(float("nan"),37),(60,30)]:
                with self.assertRaises(ValueError):await service.points(213,"Ozon",lat,lon)
            fetch.assert_not_awaited()

    async def test_upstream_failure_is_explained_without_leaking_response(self):
        service=PickupService()
        with patch("httpx.AsyncClient.get",AsyncMock(side_effect=httpx.ConnectError("private connection details"))):
            with self.assertRaisesRegex(RuntimeError,"временно недоступны"):await service._json({})
            with self.assertRaisesRegex(RuntimeError,"полминуты"):await service._json({})


class PickupApiTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(app);self.addCleanup(self.client.close)

    def test_invalid_city_and_market_do_not_call_geocoder(self):
        with patch("src.parcers.pickup.pickup_service._json",AsyncMock()) as fetch:
            for params in [{"region_id":999999,"marketplace":"Ozon"},{"region_id":213,"marketplace":"Other"}]:
                self.assertEqual(self.client.get("/api/pickup-points",params=params).status_code,422)
            fetch.assert_not_awaited()

    def test_endpoint_forwards_area_and_upstream_error_is_retryable(self):
        with patch("src.parcers.api.pickup_service.points",AsyncMock(return_value={"points":[]})) as method:
            r=self.client.get("/api/pickup-points",params={"region_id":213,"marketplace":"Ozon","lat":55.75,"lon":37.62,"radius":3})
            self.assertEqual(r.status_code,200);method.assert_awaited_once_with(213,"Ozon",55.75,37.62,3)
            method.side_effect=RuntimeError("Попробуйте позже")
            r=self.client.get("/api/pickup-points",params={"region_id":213,"marketplace":"Ozon"})
            self.assertEqual(r.status_code,503);self.assertEqual(r.headers["Retry-After"],"30")

    def test_suggestions_require_query_and_forward_city(self):
        with patch("src.parcers.api.pickup_service.suggest",AsyncMock(return_value={"suggestions":[]})) as method:
            self.assertEqual(self.client.get("/api/address-suggestions",params={"region_id":213,"q":"Тв"}).status_code,422)
            self.assertEqual(self.client.get("/api/address-suggestions",params={"region_id":213,"q":"Тверская"}).status_code,200)
            method.assert_awaited_once_with(213,"Тверская")

    def test_only_public_map_key_is_exposed_and_config_is_not_cached(self):
        with patch("src.parcers.api.yandex_keys",return_value={"YANDEX_MAPS_API_KEY":"browser-test-key","YANDEX_SUGGEST_API_KEY":"server-test-secret"}):
            response=self.client.get("/api/map-config")
            self.assertEqual(response.json(),{"provider":"yandex","api_key":"browser-test-key","yandex_suggest":True})
            self.assertNotIn("server-test-secret",response.text)
            self.assertEqual(response.headers["Cache-Control"],"no-store")


class YandexSuggestTests(unittest.IsolatedAsyncioTestCase):
    async def test_yandex_suggest_returns_safe_labels_and_keeps_server_key_private(self):
        service=PickupService()
        response=httpx.Response(200,json={"results":[{"title":{"text":"Тверская улица, 7"},"address":{"formatted_address":"Москва, Тверская улица, 7"}}]},request=httpx.Request("GET","https://suggest-maps.yandex.ru/v1/suggest"))
        with patch("httpx.AsyncClient.get",AsyncMock(return_value=response)) as request:
            data=await service._yandex_suggest({"name":"Москва"},"Тверская",(55.75,37.62),"server-test-secret")
            self.assertEqual(data["suggestions"],[{"label":"Москва, Тверская улица, 7","provider":"yandex"}])
            self.assertNotIn("server-test-secret",str(data))
            self.assertEqual(request.call_args.kwargs["params"]["ll"],"37.62,55.75")

    async def test_configured_yandex_suggest_does_not_silently_switch_provider(self):
        service=PickupService()
        with patch.object(service,"city",AsyncMock(return_value=({"id":213,"name":"Москва"},(55.75,37.62)))),patch("src.parcers.pickup.yandex_keys",return_value={"YANDEX_MAPS_API_KEY":"browser-test-key","YANDEX_SUGGEST_API_KEY":"server-test-secret"}),patch.object(service,"_yandex_suggest",AsyncMock(side_effect=RuntimeError("Подсказки недоступны"))),patch.object(service,"_json",AsyncMock()) as fallback:
            with self.assertRaisesRegex(RuntimeError,"Подсказки недоступны"):await service.suggest(213,"Тверская")
            fallback.assert_not_awaited()
