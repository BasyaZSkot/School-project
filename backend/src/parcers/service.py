from __future__ import annotations

import asyncio
from collections import defaultdict

from .base import Offer, SearchAdapter, normalize_title, offer_group_key
from .ozon import OzonAdapter
from .wb import WildberriesAdapter
from .ym import YandexMarketAdapter


class MarketplaceSearchService:
    def __init__(
        self,
        adapters: list[SearchAdapter] | None = None,
        provider_timeout: float = 12.0,
    ):
        self.adapters = adapters if adapters is not None else [
            OzonAdapter.from_env(),
            WildberriesAdapter.from_env(),
            YandexMarketAdapter.from_env(),
        ]
        self.provider_timeout = provider_timeout

    async def _search_one(self, adapter: SearchAdapter, query: str, limit: int):
        return await asyncio.wait_for(
            adapter.search(query, limit),
            timeout=self.provider_timeout,
        )

    async def search(self, query: str, limit: int = 20) -> dict:
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        results = await asyncio.gather(
            *(self._search_one(adapter, query, limit) for adapter in self.adapters),
            return_exceptions=True,
        )

        provider_results = []
        offers: list[Offer] = []
        seen: set[tuple[str, str]] = set()
        for adapter, result in zip(self.adapters, results):
            if isinstance(result, BaseException):
                error_name = "timeout" if isinstance(result, asyncio.TimeoutError) else type(result).__name__
                provider_results.append({
                    "marketplace": adapter.marketplace,
                    "status": "error",
                    "search_url": "",
                    "offers": [],
                    "message": f"Источник временно недоступен ({error_name}).",
                })
                continue

            provider_results.append(result.to_dict())
            for offer in result.offers:
                identity = (offer.marketplace, offer.external_id or offer.url)
                if identity not in seen:
                    seen.add(identity)
                    offers.append(offer)

        grouped: dict[str, list[Offer]] = defaultdict(list)
        for offer in offers:
            grouped[offer_group_key(offer)].append(offer)

        products = []
        for key, product_offers in grouped.items():
            # Prices in different currencies must never be compared numerically.
            product_offers.sort(key=lambda item: (item.currency, item.price))
            lowest_by_currency = {}
            for offer in product_offers:
                lowest_by_currency.setdefault(offer.currency, offer.price)
            products.append({
                "match_key": key,
                "title": product_offers[0].title,
                "lowest_price_by_currency": lowest_by_currency,
                "offers": [
                    {
                        "marketplace": item.marketplace,
                        "title": item.title,
                        "price": item.price,
                        "currency": item.currency,
                        "url": item.url,
                        "in_stock": item.in_stock,
                        "image_url": item.image_url,
                        "external_id": item.external_id,
                    }
                    for item in product_offers
                ],
            })
        products.sort(key=lambda item: normalize_title(item["title"]))

        return {
            "query": query,
            "providers": provider_results,
            "products": products,
            "total_offers": len(offers),
            "notice": (
                "Цены и наличие отображаются только из подключённых разрешённых "
                "источников. Пока для неподключённых площадок доступны прямые ссылки."
            ),
        }
