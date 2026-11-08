from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import httpx

from .base import MAX_PROVIDER_LIMIT, Offer, SearchAdapter, normalize_title, offer_group_key
from .ozon import OzonAdapter
from .transport import BlockedError
from .wb import WildberriesAdapter
from .ym import YandexMarketAdapter

# How many raw offers we are willing to request from one provider for one
# search call. Ozon/WB only ever fetch a single public page regardless of
# this number, so raising it does not add extra requests for them. Yandex
# Market's adapter crawls a handful of its own pages to try to fill the
# request, bounded by its own page loop, so this cap is a safety ceiling on
# top of that, not a multiplier on network calls.
PROVIDER_FETCH_CAP = MAX_PROVIDER_LIMIT
SEARCH_SESSION_TTL_SECONDS = 600
MAX_SEARCH_SESSIONS = 100


class MarketplaceSearchService:
    def __init__(self, adapters: list[SearchAdapter] | None = None, provider_timeout: float = 25.0):
        self.adapters = adapters if adapters is not None else [
            OzonAdapter.from_env(),
            WildberriesAdapter.from_env(),
            YandexMarketAdapter.from_env(),
        ]
        self.provider_timeout = provider_timeout
        self._search_sessions: dict[str, dict] = {}

    @staticmethod
    def _merge_provider_offers(existing: list[Offer], incoming: list[Offer]) -> list[Offer]:
        merged = list(existing)
        indexes = {offer.external_id or offer.url: index for index, offer in enumerate(merged)}
        for offer in incoming:
            identity = offer.external_id or offer.url
            if identity in indexes:
                merged[indexes[identity]] = offer
            else:
                indexes[identity] = len(merged)
                merged.append(offer)
        return merged

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

    async def search(
        self, query: str, limit: int = 20, offset: int = 0,
        session_id: str | None = None,
    ) -> dict:
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        max_offset = PROVIDER_FETCH_CAP * 3
        if not 0 <= offset <= max_offset:
            raise ValueError(f"offset must be between 0 and {max_offset}")

        # A UI search session keeps the successfully fetched provider prefixes.
        # Some marketplaces can temporarily fail between page clicks; retaining
        # the last good prefix prevents that failure from erasing the result set.
        offers_by_marketplace: dict[str, list[Offer]] = {}
        more_by_marketplace: dict[str, bool] = {}
        product_order: list[str] = []
        now = time.monotonic()
        for key, saved in list(self._search_sessions.items()):
            if now - saved["updated_at"] > SEARCH_SESSION_TTL_SECONDS:
                del self._search_sessions[key]
        if session_id:
            saved = self._search_sessions.get(session_id)
            if saved and saved["query"] == query:
                offers_by_marketplace = {
                    name: list(items) for name, items in saved["offers"].items()
                }
                more_by_marketplace = dict(saved["has_more"])
                product_order = list(saved.get("product_order", []))

        # Fetch enough records from each provider to assemble the requested
        # global page after cross-marketplace grouping and deduplication.
        provider_limit = min(PROVIDER_FETCH_CAP, offset + limit + 1)
        results = await asyncio.gather(
            *(self._search_one(adapter, query, provider_limit) for adapter in self.adapters),
            return_exceptions=True,
        )
        provider_results = []
        provider_may_have_more = False
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
                        message = f"HTTP {code}: площадка ограничила автоматический запрос даже после повторных попыток; откройте поиск на сайте."
                    else:
                        message = f"HTTP {code}: площадка временно не ответила."
                elif isinstance(result, httpx.TimeoutException):
                    message = (
                        "timeout: площадка не отвечает на запросы с этого IP-адреса. "
                        "Ozon и Wildberries часто молча отбрасывают соединения из-за "
                        "пределов РФ; задайте прокси в MULTIMARKET_PROXY_URLS "
                        "или откройте поиск на сайте."
                    )
                elif isinstance(result, BlockedError):
                    status = "policy_restricted"
                    message = "Площадка показала страницу проверки (антибот/капча) вместо результатов; откройте поиск на сайте."
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
            status = result.status.value if hasattr(result.status, "value") else str(result.status)
            if session_id:
                current = offers_by_marketplace.setdefault(adapter.marketplace, [])
                if result.offers:
                    offers_by_marketplace[adapter.marketplace] = self._merge_provider_offers(
                        current, result.offers
                    )
                    if status == "ready":
                        more_by_marketplace[adapter.marketplace] = (
                            result.has_more if result.has_more is not None
                            else len(result.offers) >= provider_limit
                        )
                    elif result.has_more is not None:
                        more_by_marketplace[adapter.marketplace] = result.has_more
                elif status in {"ready", "no_results"}:
                    # Explicit pagination metadata takes precedence over an empty page.
                    more_by_marketplace[adapter.marketplace] = (
                        result.has_more if result.has_more is not None else False
                    )
            else:
                # A provider that filled its whole quota probably has more cards.
                if result.has_more is not None:
                    provider_may_have_more = provider_may_have_more or result.has_more
                elif len(result.offers) >= provider_limit:
                    provider_may_have_more = True
                for offer in result.offers:
                    identity = (offer.marketplace, offer.external_id or offer.url)
                    if identity not in seen:
                        seen.add(identity)
                        offers.append(offer)

        if session_id:
            offers = [
                offer
                for adapter in self.adapters
                for offer in offers_by_marketplace.get(adapter.marketplace, [])
            ]
            provider_may_have_more = any(more_by_marketplace.values())
            self._search_sessions[session_id] = {
                "query": query,
                "offers": offers_by_marketplace,
                "has_more": more_by_marketplace,
                "product_order": product_order,
                "updated_at": time.monotonic(),
            }
            if len(self._search_sessions) > MAX_SEARCH_SESSIONS:
                oldest = min(
                    self._search_sessions,
                    key=lambda key: self._search_sessions[key]["updated_at"],
                )
                if oldest != session_id:
                    del self._search_sessions[oldest]

        # Match the same listing across different marketplaces, but never
        # collapse two distinct listings from one marketplace into one card.
        # If several same-market listings share a GTIN/title, pair them in
        # stable order with listings from other marketplaces where possible.
        grouped: dict[str, list[list[Offer]]] = defaultdict(list)
        for offer in offers:
            buckets = grouped[offer_group_key(offer)]
            product_offers = next(
                (bucket for bucket in buckets
                 if all(item.marketplace != offer.marketplace for item in bucket)),
                None,
            )
            if product_offers is None:
                product_offers = []
                buckets.append(product_offers)
            product_offers.append(offer)

        products = []
        for key, product_buckets in grouped.items():
            for bucket_index, product_offers in enumerate(product_buckets):
                product_offers.sort(key=lambda item: (item.currency, item.price))
                lowest_by_currency = {}
                for offer in product_offers:
                    lowest_by_currency.setdefault(offer.currency, offer.price)
                products.append({
                    "product_id": f"{key}:{bucket_index}",
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
                        "description": item.description,
                        "rating": item.rating,
                        "review_count": item.review_count,
                        "specifications": item.specifications,
                        "reviews": item.reviews,
                    } for item in product_offers],
                })
        if session_id:
            # New provider prefixes can discover products that sort before
            # already displayed cards. Keep the first-seen order for this
            # search session so offset-based pages never repeat or skip cards.
            session = self._search_sessions[session_id]
            products_by_id = {item["product_id"]: item for item in products}
            ordered_ids = [
                product_id for product_id in session["product_order"]
                if product_id in products_by_id
            ]
            known_ids = set(ordered_ids)
            new_products = sorted(
                (item for item in products if item["product_id"] not in known_ids),
                key=lambda item: normalize_title(item["title"]),
            )
            ordered_ids.extend(item["product_id"] for item in new_products)
            session["product_order"] = ordered_ids
            products = [products_by_id[product_id] for product_id in ordered_ids]
        else:
            products.sort(key=lambda item: normalize_title(item["title"]))
        total_products = len(products)
        page_products = products[offset:offset + limit]
        # Grouping merges offers, so the product count alone can drop below a
        # full page even though providers still have more cards to give.
        # provider_limit == PROVIDER_FETCH_CAP is the most we ever request, so
        # nothing is left to ask for then.
        retryable = bool(
            session_id
            and offset > 0
            and not page_products
            and provider_may_have_more
            and provider_limit < PROVIDER_FETCH_CAP
        )
        has_more = total_products > offset + limit or (
            provider_may_have_more and provider_limit < PROVIDER_FETCH_CAP
        ) or retryable
        # True only once every provider has returned fewer offers than we
        # asked for, i.e. we did not just hit our own request size and stop
        # early. We always ask for one extra item beyond the current page
        # (offset + limit + 1) to cheaply learn "is there at least one more
        # product?" -- so on a typical page, total_products is NOT the real
        # total and must not be read as one.
        exact_total = not provider_may_have_more
        return {
            "query": query,
            "providers": provider_results,
            "products": page_products,
            "offset": offset,
            "limit": limit,
            "total_products": total_products,
            "exact_total": exact_total,
            "has_more": has_more,
            "retryable": retryable,
            "total_offers": len(offers),
            "notice": None if offers else "Поиск завершён, но площадки не вернули читаемые карточки товаров. Попробуйте изменить запрос.",
        }
