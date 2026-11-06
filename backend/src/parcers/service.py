from __future__ import annotations

import asyncio

import httpx

from .base import Offer, SearchAdapter, normalize_title, offer_group_key
from .ozon import OzonAdapter
from .wb import WildberriesAdapter
from .ym import YandexMarketAdapter


class MarketplaceSearchService:
    def __init__(self, adapters: list[SearchAdapter] | None = None, provider_timeout: float = 12.0):
        self.adapters = adapters if adapters is not None else [
            OzonAdapter.from_env(),
            WildberriesAdapter.from_env(),
            YandexMarketAdapter.from_env(),
        ]
        self.provider_timeout = provider_timeout

    async def parse_product(self, marketplace: str, product_url: str) -> Offer | None:
        adapter = next(
            (item for item in self.adapters if item.marketplace == marketplace),
            None,
        )
        parser = getattr(adapter, "parse_product", None) if adapter else None
        if not callable(parser):
            return None
        return await asyncio.wait_for(parser(product_url), timeout=self.provider_timeout)

    async def _search_one(self, adapter: SearchAdapter, query: str, limit: int):
        return await asyncio.wait_for(adapter.search(query, limit), timeout=self.provider_timeout)

    async def search(self, query: str, limit: int = 20, offset: int = 0) -> dict:
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if not 0 <= offset <= 150:
            raise ValueError("offset must be between 0 and 150")

        # Fetch enough records from each provider to assemble the requested
        # global page after cross-marketplace grouping and deduplication.
        provider_limit = min(50, offset + limit + 1)
        results = await asyncio.gather(
            *(self._search_one(adapter, query, provider_limit) for adapter in self.adapters),
            return_exceptions=True,
        )
        provider_results = []
        offers: list[Offer] = []
        seen: set[tuple[str, str]] = set()
        for adapter, result in zip(self.adapters, results):
            if isinstance(result, Exception):
                error_name = "timeout" if isinstance(result, asyncio.TimeoutError) else type(result).__name__
                search_url = ""
                if hasattr(adapter, "search_url"):
                    from urllib.parse import quote_plus
                    search_url = adapter.search_url.format(query=quote_plus(query))
                elif hasattr(adapter, "build_search_url"):
                    search_url = adapter.build_search_url(query)
                status = "error"
                if isinstance(result, asyncio.TimeoutError):
                    message = "timeout: площадка не ответила за отведённое время."
                elif isinstance(result, httpx.HTTPStatusError):
                    code = result.response.status_code
                    if code in (401, 403, 429, 498):
                        status = "policy_restricted"
                        message = f"HTTP {code}: площадка ограничила автоматический запрос; откройте поиск на сайте."
                    else:
                        message = f"HTTP {code}: площадка временно не ответила."
                elif isinstance(result, httpx.RequestError):
                    message = "Сетевая ошибка при обращении к площадке."
                else:
                    message = "Площадка временно не ответила. Попробуйте ещё раз."
                provider_results.append({
                    "marketplace": adapter.marketplace,
                    "status": status,
                    "search_url": search_url,
                    "offers": [],
                    "message": message,
                })
                continue
            provider_results.append(result.to_dict())
            for offer in result.offers:
                identity = (offer.marketplace, offer.url)
                if identity not in seen:
                    seen.add(identity)
                    offers.append(offer)

        # A comparison group may contain at most one offer from each marketplace.
        # Keep same-marketplace listings separate so they are not mistaken for
        # cross-market price comparisons.
        grouped: list[tuple[str, list[Offer]]] = []
        for offer in offers:
            key = offer_group_key(offer)
            matching = next(
                (
                    product_offers
                    for group_key, product_offers in grouped
                    if group_key == key
                    and all(item.marketplace != offer.marketplace for item in product_offers)
                ),
                None,
            )
            if matching is None:
                grouped.append((key, [offer]))
            else:
                matching.append(offer)

        products = []
        for key, product_offers in grouped:
            product_offers.sort(key=lambda item: (item.currency, item.price))
            lowest_by_currency = {}
            for offer in product_offers:
                lowest_by_currency.setdefault(offer.currency, offer.price)
            products.append({
                "match_key": key,
                "title": product_offers[0].title,
                "lowest_price_by_currency": lowest_by_currency,
                "offers": [{
                    "marketplace": item.marketplace,
                    "title": item.title,
                    "price": item.price,
                    "currency": item.currency,
                    "url": item.url,
                    "in_stock": item.in_stock,
                    "image_url": item.image_url,
                    "external_id": item.external_id,
                } for item in product_offers],
            })
        products.sort(key=lambda item: normalize_title(item["title"]))
        total_products = len(products)
        page_products = products[offset:offset + limit]
        has_more = total_products > offset + limit
        return {
            "query": query,
            "providers": provider_results,
            "products": page_products,
            "offset": offset,
            "limit": limit,
            "total_products": total_products,
            "has_more": has_more,
            "total_offers": len(offers),
            "notice": None if offers else "Поиск завершён, но площадки не вернули читаемые карточки товаров. Попробуйте изменить запрос.",
        }
