"""Public OSM pickup locations and address autocomplete through Photon.

API: https://github.com/komoot/photon/blob/master/docs/api-v1.md
The public demo is for modest traffic; deployments can configure their own server.
These are map locations, not a promise that a marketplace accepts a given order.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import math
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

from .regions import get_region

MARKETPLACES = ("Яндекс Маркет", "Ozon", "Wildberries")
SOURCE = {"name": "OpenStreetMap", "url": "https://www.openstreetmap.org/copyright", "license": "ODbL"}
NOTICE = "Пункты из OpenStreetMap могут быть указаны не все. Доступность товара и доставку в выбранный ПВЗ подтвердит маркетплейс при оформлении."


def yandex_keys():
    # Read .env on demand so adding keys does not require a server restart.
    values = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
    return {name: (os.getenv(name) or values.get(name) or "").strip()
            for name in ("YANDEX_MAPS_API_KEY", "YANDEX_SUGGEST_API_KEY")}


def distance_km(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dlat, dlon = b - a, math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def _position(feature):
    geometry = feature.get("geometry")
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if not isinstance(coordinates, list) or len(coordinates) != 2:
        return None
    lon, lat = coordinates
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lat, lon)):
        return None
    return (lat, lon) if -85 <= lat <= 85 and -180 <= lon <= 180 else None


def _text(value, limit=200):
    return " ".join(str(value or "").split())[:limit]


def _address(properties):
    street = " ".join(filter(None, [_text(properties.get("street")), _text(properties.get("housenumber"), 40)]))
    return ", ".join(dict.fromkeys(filter(None, [street, _text(properties.get("city") or properties.get("locality"))])))


def _brand_matches(name, marketplace):
    name = name.casefold().replace("ё", "е")
    patterns = {"Яндекс Маркет": r"(?:яндекс[ ._-]*маркет|yandex[ ._-]*market)",
                "Ozon": r"\b(?:ozon|озон)\b", "Wildberries": r"\b(?:wildberries|вайлдберриз|вб|wb)\b"}
    return bool(re.search(patterns[marketplace], name))


def normalize_points(features, marketplace, region, center, radius):
    points, seen = [], set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        p, pos = feature.get("properties") or {}, _position(feature)
        if not isinstance(p, dict) or pos is None or p.get("countrycode", "").upper() != "RU":
            continue
        if (p.get("osm_key"), p.get("osm_value")) not in {("shop", "outpost"), ("amenity", "parcel_locker")}:
            continue
        if not _brand_matches(_text(p.get("name")), marketplace):
            continue
        distance = distance_km(*center, *pos)
        if distance > radius:
            continue
        kind, osm_id = p.get("osm_type"), p.get("osm_id")
        if kind not in {"N", "W", "R"} or not isinstance(osm_id, int) or isinstance(osm_id, bool) or osm_id <= 0:
            continue
        key = f"osm:{kind}:{osm_id}"
        if key in seen:
            continue
        seen.add(key)
        points.append({"id": key, "marketplace": marketplace, "region_id": region["id"],
                       "name": _text(p.get("name")), "address": _address(p) or "Адрес не указан на карте",
                       "address_complete": bool(p.get("street") and p.get("housenumber")),
                       "lat": pos[0], "lon": pos[1], "distance_km": round(distance, 2),
                       "kind": "Постамат" if p.get("osm_value") == "parcel_locker" else "Пункт выдачи",
                       "source_url": f"https://www.openstreetmap.org/{ {'N':'node','W':'way','R':'relation'}[kind]}/{osm_id}"})
    return sorted(points, key=lambda point: (point["distance_km"], point["id"]))


class PickupService:
    def __init__(self):
        self._cache = OrderedDict()
        self._lock = asyncio.Lock()
        self._next_request = 0.0
        self._retry_at = 0.0

    async def _json(self, params):
        # Serialize cache misses across all clients and throttle public service use.
        async with self._lock:
            if self._retry_at > time.monotonic():
                raise RuntimeError("Карта и адресные подсказки временно недоступны. Попробуйте через полминуты.")
            await asyncio.sleep(max(0, self._next_request - time.monotonic()))
            self._next_request = time.monotonic() + 1
            url = os.getenv("MULTIMARKET_PHOTON_URL", "https://photon.komoot.io").rstrip("/") + "/api/"
            try:
                async with httpx.AsyncClient(timeout=12, headers={"User-Agent": "MultiMarket/0.5 (+https://github.com/BasyaZSkot/School-project)"}) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("features"), list):
                    raise ValueError("Invalid geocoder response")
                return data["features"][:50]
            except (httpx.HTTPError, ValueError) as exc:
                self._retry_at = time.monotonic() + 30
                raise RuntimeError("Карта и адресные подсказки временно недоступны. Попробуйте позже.") from exc

    async def _cached(self, key, params, ttl):
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            self._cache.move_to_end(key)
            return cached[1]
        # Share an in-flight request for identical searches, including failures.
        if cached and isinstance(cached[1], asyncio.Task):
            return await asyncio.shield(cached[1])
        if sum(isinstance(entry[1], asyncio.Task) for entry in self._cache.values()) >= 8:
            raise RuntimeError("Сервис адресов занят. Повторите поиск через несколько секунд.")
        async def load():
            try:
                data = await self._json(params)
                self._cache[key] = (time.monotonic() + ttl, data)
                return data
            except BaseException:
                self._cache.pop(key, None)
                raise
        task = asyncio.create_task(load())
        # Retrieve background failures if a browser cancels its only waiter.
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        self._cache[key] = (0, task)
        while len(self._cache) > 256:
            self._cache.popitem(last=False)
        return await asyncio.shield(task)

    async def city(self, region_id):
        region = get_region(region_id)
        features = await self._cached(("city", region_id), {"q": region["name"], "countrycode": "RU", "layer": "city", "limit": 5}, 86400 * 7)
        for feature in features:
            p = feature.get("properties") or {}
            if isinstance(p, dict) and _text(p.get("name")).casefold().replace("ё", "е") == region["name"].casefold().replace("ё", "е") and _position(feature):
                return region, _position(feature)
        raise RuntimeError("Не удалось найти город на карте. Попробуйте позже.")

    async def points(self, region_id, marketplace, lat=None, lon=None, radius=4):
        if marketplace not in MARKETPLACES:
            raise ValueError("Выберите маркетплейс из списка")
        region, city = await self.city(region_id)
        if (lat is None) != (lon is None):
            raise ValueError("Укажите обе координаты")
        center = city if lat is None else (lat, lon)
        if not all(math.isfinite(v) for v in (*center, radius)) or not .5 <= radius <= 6 or distance_km(*city, *center) > 80:
            raise ValueError("Выберите область рядом с выбранным городом")
        lat, lon = (round(v, 4) for v in center)
        # Bounding box only limits the geocoder; exact radial filtering is below.
        dy, dx = radius / 111, radius / (111 * max(.1, math.cos(math.radians(lat))))
        params = [("q", marketplace), ("limit", 50), ("lat", lat), ("lon", lon),
                  ("bbox", f"{lon-dx},{lat-dy},{lon+dx},{lat+dy}"),
                  ("osm_tag", "shop:outpost"), ("osm_tag", "amenity:parcel_locker")]
        features = await self._cached(("points", region_id, marketplace, lat, lon, radius), params, 21600)
        return {"region": region, "center": {"lat": lat, "lon": lon}, "radius_km": radius,
                "points": normalize_points(features, marketplace, region, (lat, lon), radius),
                "limited": len(features) >= 50, "source": SOURCE, "notice": NOTICE}

    async def suggest(self, region_id, query):
        region, center = await self.city(region_id)
        query = _text(query, 160)
        if len(query) < 3:
            return {"suggestions": [], "source": SOURCE}
        lat, lon = center
        keys = yandex_keys()
        if keys["YANDEX_MAPS_API_KEY"] and keys["YANDEX_SUGGEST_API_KEY"]:
            return await self._yandex_suggest(region, query, center, keys["YANDEX_SUGGEST_API_KEY"])
        params = {"q": f"{region['name']}, {query}", "lat": lat, "lon": lon, "limit": 6, "countrycode": "RU"}
        features = await self._cached(("address", region_id, query.casefold()), params, 3600)
        results, seen = [], set()
        for f in features:
            p, pos = f.get("properties") or {}, _position(f)
            if not isinstance(p, dict) or not pos or distance_km(*center, *pos) > 80:
                continue
            label = _address(p)
            if not p.get("street"):
                label = ", ".join(filter(None, [_text(p.get("name")), _text(p.get("city"))]))
            if not label or label in seen:
                continue
            seen.add(label)
            results.append({"label": label, "lat": pos[0], "lon": pos[1]})
        return {"suggestions": results, "source": SOURCE}

    async def _yandex_suggest(self, region, query, center, key):
        lat, lon = center
        params = {"apikey":key, "text": f"{region['name']}, {query}", "ll":f"{lon},{lat}",
                  "results":6,"lang":"ru", "countries":"ru", "types":"geo", "print_address":1,"attrs":"uri"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("https://suggest-maps.yandex.ru/v1/suggest", params=params)
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid suggest response")
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("Подсказки Яндекса временно недоступны. Можно выбрать ПВЗ на карте или в списке.") from exc
        suggestions = []
        for item in (data.get("results") or [])[:6]:
            address = item.get("address") or {}
            label = address.get("formatted_address") or ", ".join(filter(None, [item.get("title",{}).get("text"),item.get("subtitle",{}).get("text")]))
            if label:
                suggestions.append({"label":_text(label,500),"provider":"yandex"})
        return {"suggestions": suggestions,"source":{"name":"Яндекс Карты","url":"https://yandex.ru/maps/"}}


pickup_service = PickupService()
