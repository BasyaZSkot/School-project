"""Best-effort parser for publicly rendered marketplace search pages.

Only extracts product data explicitly present in a normal public HTML response.
Requests go through ``transport.ResilientFetcher`` (browser-like headers, rate
limiting, retries with backoff, optional operator-supplied proxies). It does not
log in, call private APIs, or solve CAPTCHAs.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin, urlparse

from .base import MAX_PROVIDER_LIMIT, Offer, ProviderResult, SearchStatus
from .transport import ResilientFetcher, get_shared_fetcher


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
        for key in ("@graph", "itemListElement", "mainEntity", "mainEntityOfPage", "item"):
            if key in value:
                yield from _walk(value[key])


def _as_text(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("@id") or value.get("url")
    if isinstance(value, list):
        return _as_text(value[0]) if value else None
    return str(value).strip() if value is not None else None


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    raw = re.sub(r"[^0-9.,]", "", str(value))
    if raw.count(",") + raw.count(".") > 1:
        return None
    try:
        number = float(raw.replace(",", "."))
    except ValueError:
        return None
    return number if number > 0 else None


def _review_total(value) -> int | None:
    if value is None or value == "":
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    try:
        count = int(digits)
    except ValueError:
        return None
    return count if count >= 0 else None


def _clean_description(value) -> str | None:
    text = _as_text(value)
    if not text:
        return None
    text = " ".join(text.split())
    return text[:5000] or None


def _product_metadata(item: dict) -> dict:
    aggregate = item.get("aggregateRating") or item.get("rating") or {}
    if isinstance(aggregate, list):
        aggregate = next((value for value in aggregate if isinstance(value, dict)), {})
    if not isinstance(aggregate, dict):
        aggregate = {}

    rating = _number(aggregate.get("ratingValue") or item.get("ratingValue"))
    if rating is not None and rating > 5:
        rating = None
    review_count = _review_total(
        aggregate.get("reviewCount") or aggregate.get("ratingCount")
        or item.get("reviewCount") or item.get("ratingCount")
    )

    raw_specs = item.get("additionalProperty") or item.get("specifications") or []
    if isinstance(raw_specs, dict):
        raw_specs = [raw_specs]
    specifications = []
    if isinstance(raw_specs, list):
        for prop in raw_specs:
            if not isinstance(prop, dict):
                continue
            name = _as_text(prop.get("name"))
            value = _as_text(prop.get("value") or prop.get("valueReference"))
            if name and value:
                specifications.append({"name": name[:120], "value": value[:500]})
            if len(specifications) >= 30:
                break

    raw_reviews = item.get("review") or item.get("reviews") or []
    if isinstance(raw_reviews, dict):
        raw_reviews = [raw_reviews]
    reviews = []
    if isinstance(raw_reviews, list):
        for review in raw_reviews:
            if not isinstance(review, dict):
                continue
            body = _clean_description(review.get("reviewBody") or review.get("description"))
            if not body:
                continue
            author = _as_text(review.get("author"))
            date = _as_text(review.get("datePublished"))
            review_rating = review.get("reviewRating")
            if isinstance(review_rating, list):
                review_rating = next((value for value in review_rating if isinstance(value, dict)), {})
            score = _number(review_rating.get("ratingValue")) if isinstance(review_rating, dict) else None
            reviews.append({
                "body": body[:1200],
                "author": author[:120] if author else "Покупатель",
                "date": date[:40] if date else "",
                "rating": str(score) if score is not None and score <= 5 else "",
            })
            if len(reviews) >= 10:
                break

    return {
        "description": _clean_description(item.get("description")),
        "rating": rating,
        "review_count": review_count,
        "specifications": specifications,
        "reviews": reviews,
    }


def _price_from_offer(offer: dict) -> float | None:
    candidates = [offer.get("price"), offer.get("lowPrice")]
    specification = offer.get("priceSpecification")
    if isinstance(specification, list):
        candidates.extend(
            item.get("price") for item in specification if isinstance(item, dict)
        )
    elif isinstance(specification, dict):
        candidates.append(specification.get("price"))
    for value in candidates:
        if value is None or value == "":
            continue
        # Keep decimal separators and digits only; reject ambiguous multiple separators.
        raw = re.sub(r"[^0-9.,]", "", str(value))
        if raw.count(",") + raw.count(".") > 1:
            continue
        try:
            price = float(raw.replace(",", "."))
        except ValueError:
            continue
        if price > 0:
            return price
    return None



class _MicrodataProductParser(HTMLParser):
    """Read Schema.org Product microdata from server-rendered HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.products: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._stack: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        itemtype = attrs.get("itemtype", "").lower()
        if "itemscope" in attrs and "schema.org/product" in itemtype:
            if self._current is not None:
                self.products.append(self._current)
            self._current = {}
        prop = attrs.get("itemprop")
        if self._current is not None and prop:
            value = (attrs.get("content") or attrs.get("data-price")
                     or attrs.get("href") or attrs.get("src") or attrs.get("value"))
            if value:
                self._current[prop] = value.strip()
        self._stack.append((tag, prop))

    def handle_data(self, data):
        if self._current is None or not self._stack:
            return
        prop = next((p for _, p in reversed(self._stack) if p), None)
        if prop and data.strip():
            self._current[prop] = (self._current.get(prop, "") + " " + data.strip()).strip()

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

    def close(self):
        super().close()
        if self._current is not None:
            self.products.append(self._current)
            self._current = None


class PublicHtmlSearchAdapter:
    def __init__(
        self,
        *,
        marketplace: str,
        search_url: str,
        allowed_hosts: tuple[str, ...],
        timeout: float = 10.0,
        fetcher: ResilientFetcher | None = None,
    ):
        self.marketplace = marketplace
        self.search_url = search_url
        self.allowed_hosts = allowed_hosts
        self.timeout = timeout
        self._fetcher = fetcher

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
                if not any(str(k).lower().rstrip("/").endswith("product") for k in kinds):
                    continue
                title = _as_text(item.get("name"))
                raw_url = _as_text(item.get("url") or item.get("@id"))
                product_url = self._valid_marketplace_url(raw_url, page_url) if raw_url else None
                raw_offers = item.get("offers")
                offer_list = raw_offers if isinstance(raw_offers, list) else [raw_offers]
                if not isinstance(raw_offers, (dict, list)):
                    continue
                for raw_offer in offer_list:
                    if not isinstance(raw_offer, dict):
                        continue
                    price = _price_from_offer(raw_offer)
                    if not title or not product_url or price is None or product_url in seen:
                        continue
                    currency = str(raw_offer.get("priceCurrency") or "RUB").upper()
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
                    availability = str(raw_offer.get("availability") or "").lower()
                    in_stock = True if "instock" in availability else False if "outofstock" in availability else None
                    details = _product_metadata(item)
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
                        **details,
                    ))
                    seen.add(product_url)
                    if len(offers) >= limit:
                        return offers
        if offers:
            return offers

        # Some server-rendered pages publish Schema.org microdata instead of JSON-LD.
        microdata = _MicrodataProductParser()
        microdata.feed(html)
        microdata.close()
        for item in microdata.products:
            title = item.get("name")
            raw_url = item.get("url")
            product_url = self._valid_marketplace_url(raw_url, page_url) if raw_url else None
            price = _price_from_offer({"price": item.get("price")})
            if not title or not product_url or price is None or product_url in seen:
                continue
            currency = str(item.get("priceCurrency") or "RUB").upper()
            if len(currency) != 3 or not currency.isalpha():
                currency = "RUB"
            image = item.get("image")
            image_url = urljoin(page_url, image) if image else None
            if image_url and urlparse(image_url).scheme != "https":
                image_url = None
            details = _product_metadata(item)
            offers.append(Offer(
                marketplace=self.marketplace, title=title, price=price,
                currency=currency, url=product_url, image_url=image_url,
                external_id=item.get("sku") or None,
                brand=item.get("brand") or None,
                **details,
            ))
            seen.add(product_url)
            if len(offers) >= limit:
                break
        return offers

    def _extract_product(self, html: str, page_url: str) -> Offer | None:
        expected_path = urlparse(page_url).path.rstrip("/")
        for offer in self._extract(html, page_url, 50):
            if urlparse(offer.url).path.rstrip("/") == expected_path:
                return offer
        return None

    async def _fetch_public_page(self, url: str) -> tuple[str, str]:
        fetcher = self._fetcher or get_shared_fetcher()
        page = await fetcher.fetch(url)
        if not self._valid_marketplace_url(page.url, url):
            raise ValueError("Marketplace redirected outside its own domain")
        return page.url, page.text

    async def parse_product(self, product_url: str) -> Offer | None:
        valid_url = self._valid_marketplace_url(product_url, product_url)
        if not valid_url:
            raise ValueError("Product URL is outside this marketplace")
        final_url, html = await self._fetch_public_page(valid_url)
        offer = self._extract_product(html, final_url)
        if offer is not None:
            offer.url = final_url
        return offer

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= MAX_PROVIDER_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_PROVIDER_LIMIT}")
        # Normalize whitespace without imposing a minimum query length.
        clean_query = " ".join(query.split())
        url = self.search_url.format(query=quote_plus(clean_query))
        final_url, html = await self._fetch_public_page(url)
        offers = self._extract(html, final_url, limit)
        return ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY if offers else SearchStatus.NO_RESULTS,
            search_url=url,
            offers=offers,
            message=None if offers else "Страница доступна, но карточки не опубликованы в поддерживаемой публичной разметке (JSON-LD/microdata).",
        )
