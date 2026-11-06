"""Bridge WB parser records into MultiMarket's normalized Offer contract.

This module does not perform network requests or obtain browser cookies. Supply
records from an approved/licensed data source via the async source callable.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from .base import DisabledAdapter, Offer, ProviderResult, SearchStatus

RecordSource = Callable[[str, int], Awaitable[Iterable[Any]]]


def _read(record: Any, key: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


def _rubles_from_kopecks(value: Any) -> float | None:
    try:
        kopecks = float(value)
    except (TypeError, ValueError):
        return None
    if kopecks <= 0:
        return None
    return kopecks / 100


def wb_record_to_offer(record: Any) -> Offer | None:
    """Convert one record shaped like the example WB Item model to an Offer."""
    raw_id = _read(record, "id")
    try:
        product_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    if product_id <= 0:
        return None

    title = str(_read(record, "name", "") or "").strip()
    if not title:
        return None

    # Prefer raw nested size prices: the example Pydantic model may already have
    # converted those into salePriceU/priceU when the top-level values were absent.
    price = None
    sizes = _read(record, "sizes", []) or []
    if sizes:
        size_price = _read(sizes[0], "price")
        if size_price:
            price = _rubles_from_kopecks(
                _read(size_price, "product") or _read(size_price, "basic")
            )
    if price is None:
        price = _rubles_from_kopecks(_read(record, "salePriceU"))
    if price is None:
        price = _rubles_from_kopecks(_read(record, "priceU"))
    if price is None:
        return None

    image_links = str(_read(record, "image_links", "") or "")
    image_url = next(
        (part.strip().lstrip("\u200b") for part in image_links.split(";")
         if part.strip().lstrip("\u200b").startswith("https://")),
        None,
    )
    quantity = _read(record, "totalQuantity")
    try:
        in_stock = int(quantity) > 0 if quantity is not None else None
    except (TypeError, ValueError):
        in_stock = None

    brand = str(_read(record, "brand", "") or "").strip() or None
    return Offer(
        marketplace="Wildberries",
        title=title,
        price=price,
        currency="RUB",
        url=f"https://www.wildberries.ru/catalog/{product_id}/detail.aspx",
        external_id=str(product_id),
        brand=brand,
        gtin=None,
        in_stock=in_stock,
        image_url=image_url,
    )


class WildberriesAdapter(DisabledAdapter):
    """WB adapter with an injectable approved source; disabled by default."""

    marketplace = "Wildberries"
    base_search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
    status = SearchStatus.ACCESS_REQUIRED
    reason = (
        "Для автоматической выдачи нужны разрешённый API, лицензированный фид "
        "или письменное разрешение. Пока доступна прямая ссылка на поиск."
    )

    def __init__(self, source: RecordSource | None = None):
        self.source = source

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        if self.source is None:
            return await super().search(query, limit)

        if not query.strip():
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        records = await self.source(query, limit)
        offers = []
        for record in records:
            offer = wb_record_to_offer(record)
            if offer is not None:
                offers.append(offer)
            if len(offers) >= limit:
                break

        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY,
            search_url=self.build_search_url(query),
            offers=offers,
            message=None if offers else "Источник ответил, но подходящих товаров не найдено.",
        )
