import os
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlparse, urlunparse

from .base import Offer, ProviderResult, SearchStatus
from .feed import JsonFeedAdapter
from .public_html import PublicHtmlSearchAdapter, _price_from_offer


class _YandexProductStateParser(HTMLParser):
    # Read public data-auto fields used by Grex's Yandex product parser.
    _targets = {
        "productCardTitle",
        "snippet-price-old",
        "snippet-price-current",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._tags = []
        self._captures = []
        self.values = {}

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self._tags.append(tag)
        target = dict(attrs).get("data-auto")
        if target in self._targets:
            self._captures.append({
                "tag": tag,
                "depth": len(self._tags),
                "target": target,
                "parts": [],
            })

    def handle_data(self, data):
        for capture in self._captures:
            capture["parts"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        close_index = next(
            (index for index in range(len(self._tags) - 1, -1, -1)
             if self._tags[index] == tag),
            None,
        )
        if close_index is None:
            return
        depth = close_index + 1
        remaining = []
        for capture in self._captures:
            if capture["tag"] == tag and capture["depth"] == depth:
                value = " ".join(" ".join(capture["parts"]).split())
                if value:
                    self.values.setdefault(capture["target"], []).append(value)
            else:
                remaining.append(capture)
        self._captures = remaining
        del self._tags[close_index:]


class _YandexSearchCardsParser(HTMLParser):
    """Read titles, prices, links and images from public search-card markup."""

    _text_targets = {
        "snippet-title": "title",
        "snippet-price-current": "price",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._tags = []
        self._captures = []
        self._card = None
        self.cards = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        depth = len(self._tags) + 1
        target = attrs.get("data-auto")

        if target == "searchOrganic":
            self._finish_card()
            self._card = {
                "tag": tag,
                "depth": depth,
                "title": [],
                "price": [],
                "url": None,
                "image_url": None,
            }
        elif self._card is not None:
            field = self._text_targets.get(target)
            if field:
                self._captures.append({
                    "tag": tag,
                    "depth": depth,
                    "field": field,
                    "parts": [],
                })

            href = attrs.get("href", "")
            if (
                self._card["url"] is None
                and tag == "a"
                and ("/card/" in href or "/product/" in href)
            ):
                self._card["url"] = href

            if self._card["image_url"] is None and tag == "img":
                image = attrs.get("src") or attrs.get("data-src")
                if not image and attrs.get("srcset"):
                    image = attrs["srcset"].split(",", 1)[0].strip().split(" ", 1)[0]
                self._card["image_url"] = image

        self._tags.append(tag)

    def handle_data(self, data):
        for capture in self._captures:
            capture["parts"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        close_index = next(
            (index for index in range(len(self._tags) - 1, -1, -1)
             if self._tags[index] == tag),
            None,
        )
        if close_index is None:
            return

        depth = close_index + 1
        remaining = []
        for capture in self._captures:
            if capture["tag"] == tag and capture["depth"] == depth:
                value = " ".join(" ".join(capture["parts"]).split())
                if value and self._card is not None:
                    self._card[capture["field"]].append(value)
            else:
                remaining.append(capture)
        self._captures = remaining

        if (
            self._card is not None
            and self._card["tag"] == tag
            and self._card["depth"] == depth
        ):
            self._finish_card()
        del self._tags[close_index:]

    def close(self):
        super().close()
        self._finish_card()

    def _finish_card(self):
        if self._card is None:
            return
        card = self._card
        self._card = None
        self._captures = []
        self.cards.append(card)


class YandexMarketAdapter(PublicHtmlSearchAdapter):
    """Yandex Market public-page connector."""

    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"
    allowed_hosts = ("market.yandex.ru",)

    def _extract(self, html: str, page_url: str, limit: int):
        parser = _YandexSearchCardsParser()
        parser.feed(html)
        parser.close()

        offers = []
        seen = set()
        for card in parser.cards:
            titles = card["title"]
            prices = card["price"]
            title = titles[0] if titles else None
            raw_url = card["url"]
            product_url = self._valid_marketplace_url(raw_url, page_url) if raw_url else None
            price = next(
                (_price_from_offer({"price": raw_price}) for raw_price in prices
                 if _price_from_offer({"price": raw_price}) is not None),
                None,
            )
            if not title or price is None or not product_url:
                continue

            parsed_url = urlparse(product_url)
            product_url = urlunparse(parsed_url._replace(query="", fragment=""))
            if product_url in seen:
                continue
            seen.add(product_url)

            raw_image = card["image_url"]
            image_url = urljoin(page_url, raw_image) if raw_image else None
            if image_url and urlparse(image_url).scheme != "https":
                image_url = None
            path_parts = [part for part in parsed_url.path.split("/") if part]
            product_id = next(
                (part for part in reversed(path_parts) if part.isdigit()),
                path_parts[-1] if path_parts else None,
            )
            offers.append(Offer(
                marketplace=self.marketplace,
                title=title,
                price=price,
                currency="RUB",
                url=product_url,
                external_id=product_id,
                image_url=image_url,
            ))
            if len(offers) >= limit:
                return offers

        return offers if offers else super()._extract(html, page_url, limit)

    @staticmethod
    def _is_challenge_page(page_url: str, html: str) -> bool:
        if urlparse(page_url).path.rstrip("/").lower() == "/showcaptcha":
            return True
        prefix = html[:30000].lower()
        return "smartcaptcha" in prefix or "checkbox-captcha" in prefix

    async def search(self, query: str, limit: int = 20):
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        clean_query = " ".join(query.split())
        search_url = self.search_url.format(query=quote_plus(clean_query))
        final_url, html = await self._fetch_public_page(search_url)
        if self._is_challenge_page(final_url, html):
            return ProviderResult(
                marketplace=self.marketplace,
                status=SearchStatus.POLICY_RESTRICTED,
                search_url=search_url,
                offers=[],
                message="Яндекс Маркет вернул страницу проверки вместо результатов поиска.",
            )

        offers = self._extract(html, final_url, limit)
        result = ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY if offers else SearchStatus.NO_RESULTS,
            search_url=search_url,
            offers=offers,
            message=None if offers else "Страница доступна, но карточки не найдены в поддерживаемой разметке.",
        )
        if result.status != SearchStatus.READY or len(result.offers) >= limit:
            return result

        offers = list(result.offers)
        seen = {offer.external_id or offer.url for offer in offers}
        base = urlparse(search_url)
        for page in range(2, 6):
            query_items = [
                (key, value) for key, value in parse_qsl(base.query, keep_blank_values=True)
                if key != "page"
            ]
            query_items.append(("page", str(page)))
            page_url = urlunparse(base._replace(query=urlencode(query_items)))
            try:
                final_url, html = await self._fetch_public_page(page_url)
            except Exception:
                result.message = "Дополнительные страницы недоступны; показаны уже найденные товары."
                break
            if self._is_challenge_page(final_url, html):
                result.message = "Для дополнительных страниц Яндекс Маркет запросил проверку; показаны найденные товары."
                break

            remaining = limit - len(offers)
            page_offers = self._extract(html, final_url, remaining)
            added = [
                offer for offer in page_offers
                if (offer.external_id or offer.url) not in seen
            ]
            if not added:
                break
            for offer in added:
                identity = offer.external_id or offer.url
                seen.add(identity)
                offers.append(offer)
                if len(offers) >= limit:
                    break
            if len(offers) >= limit:
                break

        result.offers = offers[:limit]
        if len(result.offers) < limit and result.message is None:
            result.message = "Показаны карточки с доступных публичных страниц поиска."
        return result

    def _extract_product(self, html: str, page_url: str):
        parser = _YandexProductStateParser()
        parser.feed(html)
        parser.close()
        titles = parser.values.get("productCardTitle", [])
        current_prices = parser.values.get("snippet-price-current", [])
        title = titles[0] if titles else None
        price = None
        for raw_price in current_prices:
            price = _price_from_offer({"price": raw_price})
            if price is not None:
                break
        structured = super()._extract_product(html, page_url)
        if not title or price is None:
            return structured
        product_id = re.search(r"/card/([^/]+)", urlparse(page_url).path)
        offer = Offer(
            marketplace=self.marketplace,
            title=title,
            price=price,
            currency="RUB",
            url=page_url,
            external_id=product_id.group(1) if product_id else None,
        )
        if structured is not None:
            offer.description = structured.description
            offer.rating = structured.rating
            offer.review_count = structured.review_count
            offer.specifications = structured.specifications
            offer.reviews = structured.reviews
            offer.image_url = structured.image_url
        return offer

    @classmethod
    def from_env(cls):
        feed_url = os.getenv("MULTIMARKET_YM_FEED_URL", "").strip()
        if feed_url:
            return JsonFeedAdapter(
                marketplace=cls.marketplace,
                base_search_url=cls.base_search_url,
                reason="Подключён разрешённый партнёрский источник Яндекс Маркета.",
                feed_url=feed_url,
                token=os.getenv("MULTIMARKET_YM_FEED_TOKEN", "").strip() or None,
                allowed_hosts=cls.allowed_hosts,
            )
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
