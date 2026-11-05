from __future__ import annotations

import asyncio
from collections import defaultdict

from .base import Offer, SearchAdapter, offer_group_key
from .ozon import OzonAdapter
from .wb import WildberriesAdapter
from .ym import YandexMarketAdapter


class MarketplaceSearchService:
    def __init__(self, adapters: list[SearchAdapter] | None = None):
        self.adapters = adapters or [
            OzonAdapter(),
            WildberriesAdapter(),
            YandexMarketAdapter(),
        ]

    async def search(self, query: str, limit: int = 20) -> dict:
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        results = await asyncio.gather(
            *(adapter.search(query, limit) for adapter in self.adapters),
            return_exceptions=True,
        )

        provider_results = []
        offers: list[Offer] = []
        for adapter, result in zip(self.adapters, results):
            if isinstance(result, Exception):
                provider_results.append({
                    "marketplace": adapter.marketplace,
                    "status": "error",
                    "search_url": "",
                    "offers": [],
                    "message": f"Источник временно недоступен: {type(result).__name__}",
                })
                continue
            provider_results.append(result.to_dict())
            offers.extend(result.offers)

        grouped: dict[str, list[Offer]] = defaultdict(list)
        for offer in offers:
            grouped[offer_group_key(offer)].append(offer)

        products = []
        for key, product_offers in grouped.items():
            product_offers.sort(key=lambda item: item.price)
            products.append({
                "match_key": key,
                "title": product_offers[0].title,
                "offers": [
                    {
                        "marketplace": item.marketplace,
                        "title": item.title,
                        "price": item.price,
                        "currency": item.currency,
                        "url": item.url,
                        "in_stock": item.in_stock,
                    }
                    for item in product_offers
                ],
            })
        products.sort(
            key=lambda item: min(offer["price"] for offer in item["offers"])
        )
        return {
            "query": query,
            "providers": provider_results,
            "products": products,
            "notice": (
                "Цены и наличие появятся после подключения разрешённых источников. "
                "Сейчас доступны прямые ссылки на поиск маркетплейсов."
            ),
        }
