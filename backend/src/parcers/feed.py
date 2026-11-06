"""Adapter for licensed/partner JSON feeds with a normalized payload contract."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import DisabledAdapter, Offer, ProviderResult, SearchStatus


class JsonFeedAdapter(DisabledAdapter):
    """Fetch a partner feed and normalize its records into MultiMarket offers.

    Feed URL and token must come from server environment variables, never from
    a browser request. The default contract is {"offers": [...]}; adapters may
    provide a record mapper and alternate array key for approved native feeds.
    """

    def __init__(
        self,
        *,
        marketplace: str,
        base_search_url: str,
        reason: str,
        feed_url: str,
        token: str | None = None,
        timeout: float = 8.0,
        records_key: str = "offers",
        record_mapper: Callable[[Any], Offer | None] | None = None,
        allowed_hosts: tuple[str, ...] = (),
    ):
        parsed = urlparse(feed_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Partner feed URL must use HTTPS")
        self.marketplace = marketplace
        self.base_search_url = base_search_url
        self.reason = reason
        self.feed_url = feed_url
        self.token = token
        self.timeout = timeout
        self.records_key = records_key
        self.record_mapper = record_mapper
        self.allowed_hosts = tuple(host.lower() for host in allowed_hosts)
        self.status = SearchStatus.ACCESS_REQUIRED

    def _is_allowed_marketplace_url(self, value: str) -> bool:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        return not self.allowed_hosts or any(
            parsed.hostname == host or parsed.hostname.endswith("." + host)
            for host in self.allowed_hosts
        )

    def _map_offer(self, item: dict) -> Offer | None:
        try:
            product_url = str(item["url"]).strip()
            if not self._is_allowed_marketplace_url(product_url):
                return None
            image_url = item.get("image_url")
            if image_url:
                image_parsed = urlparse(str(image_url))
                if image_parsed.scheme != "https" or not image_parsed.netloc:
                    image_url = None
            return Offer(
                marketplace=self.marketplace,
                title=str(item["title"]),
                price=float(item["price"]),
                currency=str(item.get("currency", "RUB")),
                url=product_url,
                external_id=str(item["id"]) if item.get("id") is not None else None,
                brand=str(item["brand"]) if item.get("brand") else None,
                model=str(item["model"]) if item.get("model") else None,
                gtin=str(item["gtin"]) if item.get("gtin") else None,
                in_stock=item.get("in_stock") if isinstance(item.get("in_stock"), bool) else None,
                image_url=str(image_url) if image_url else None,
            )
        except (KeyError, TypeError, ValueError):
            return None

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            response = await client.get(
                self.feed_url,
                params={"q": query, "limit": limit},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()

        records = payload.get(self.records_key, []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError(f"Partner feed must return a {self.records_key} array")

        offers = []
        for record in records:
            if self.record_mapper is not None:
                offer = self.record_mapper(record)
            elif isinstance(record, dict):
                offer = self._map_offer(record)
            else:
                offer = None
            if offer is not None and (
                offer.marketplace != self.marketplace
                or not self._is_allowed_marketplace_url(offer.url)
            ):
                offer = None
            if offer is not None:
                offers.append(offer)
            if len(offers) >= limit:
                break

        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY if offers else SearchStatus.NO_RESULTS,
            search_url=self.build_search_url(query),
            offers=offers,
            message=None if offers else "Источник ответил, но предложений не найдено.",
        )
