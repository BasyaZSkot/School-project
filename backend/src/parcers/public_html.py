"""Best-effort parser for publicly rendered marketplace search pages.

This adapter performs a normal HTTPS GET and extracts Schema.org Product data
from JSON-LD. It does not log in, call private APIs, solve challenges, or evade
access controls. Marketplace HTML is not a stable API, so empty results are a
valid outcome when a page does not expose structured product data.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from .base import Offer, ProviderResult, SearchStatus


class _JsonLdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_jsonld = False
        self._parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            attrs_map = dict(attrs)
            if "ld+json" in attrs_map.get("type", "").lower():
                self._in_jsonld = True
                self._parts = []

    def handle_data(self, data):
        if self._in_jsonld:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._in_jsonld:
            self.documents.append("".join(self._parts))
            self._in_jsonld = False
            self._parts = []


def _walk(value):
    if isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk(graph)
        for key in ("itemListElement", "mainEntity", "mainEntityOfPage"):
            if key in value:
                yield from _walk(value[key])
        item = value.get("item")
        if item is not None:
            yield from _walk(item)


def _as_text(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("@id")
    if isinstance(value, list):
        return _as_text(value[0]) if value else None
    return str(value).strip() if value is not None else None


class PublicHtmlSearchAdapter:
    def __init__(self, *, marketplace: str, search_url: str, allowed_hosts: tuple[str, ...], timeout: float = 10.0):
        self.marketplace = marketplace
        self.search_url = search_url
        self.allowed_hosts = allowed_hosts
        self.timeout = timeout

    def _valid_marketplace_url(self, value: str, base: str) -> str | None:
        absolute = urljoin(base, value)
        parsed = urlparse(absolute)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        if not any(parsed.hostname == host or parsed.hostname.endswith("." + host) for host in self.allowed_hosts):
            return None
        return absolute

    def _extract(self, html: str, page_url: str, limit: int) -> list[Offer]:
        parser = _JsonLdParser()
        parser.feed(html)
        offers: list[Offer] = []
        seen: set[str] = set()
        for raw in parser.documents:
            try:
                document = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            for item in _walk(document):
                kind = item.get("@type", [])
                kinds = kind if isinstance(kind, list) else [kind]
                if not any(str(k).lower().endswith("product") for k in kinds):
                    continue
                title = _as_text(item.get("name"))
                raw_url = _as_text(item.get("url") or item.get("@id"))
                product_url = self._valid_marketplace_url(raw_url, page_url) if raw_url else None
                raw_offers = item.get("offers")
                if isinstance(raw_offers, list):
                    raw_offers = raw_offers[0] if raw_offers else None
                if not isinstance(raw_offers, dict):
                    continue
                price_value = raw_offers.get("price") or raw_offers.get("lowPrice")
                try:
                    price = float(re.sub(r"[^0-9.,]", "", str(price_value)).replace(",", "."))
                except (TypeError, ValueError):
                    continue
                if not title or not product_url or price <= 0 or product_url in seen:
                    continue
                currency = str(raw_offers.get("priceCurrency") or "RUB").upper()
                if len(currency) != 3 or not currency.isalpha():
                    currency = "RUB"
                image = item.get("image")
                if isinstance(image, list):
                    image = image[0] if image else None
                if isinstance(image, dict):
                    image = image.get("url")
                image_url = urljoin(page_url, str(image)) if image else None
                if image_url and urlparse(image_url).scheme != "https":
                    image_url = None
                brand = _as_text(item.get("brand"))
                availability = str(raw_offers.get("availability") or "").lower()
                in_stock = True if "instock" in availability else False if "outofstock" in availability else None
                offers.append(Offer(
                    marketplace=self.marketplace,
                    title=title,
                    price=price,
                    currency=currency,
                    url=product_url,
                    external_id=str(item.get("sku") or item.get("productID") or "") or None,
                    brand=brand,
                    gtin=str(item.get("gtin13") or item.get("gtin") or "") or None,
                    in_stock=in_stock,
                    image_url=image_url,
                ))
                seen.add(product_url)
                if len(offers) >= limit:
                    return offers
        return offers

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        from urllib.parse import quote_plus
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        url = self.search_url.format(query=quote_plus(query))
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
            "User-Agent": "MultiMarket/1.0 (public search page reader)",
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            final_url = str(response.url)
            if not self._valid_marketplace_url(final_url, url):
                raise ValueError("Marketplace redirected outside its own domain")
            offers = self._extract(response.text, final_url, limit)
        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY,
            search_url=url,
            offers=offers,
            message=None if offers else "Страница открылась, но не предоставила структурированные карточки товаров.",
        )
