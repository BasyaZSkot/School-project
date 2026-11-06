import os
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from .base import Offer
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


class YandexMarketAdapter(PublicHtmlSearchAdapter):
    """Yandex Market public-page connector."""

    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"
    allowed_hosts = ("market.yandex.ru",)

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
        if title and price is not None:
            product_id = re.search(r"/card/([^/]+)", urlparse(page_url).path)
            return Offer(
                marketplace=self.marketplace,
                title=title,
                price=price,
                currency="RUB",
                url=page_url,
                external_id=product_id.group(1) if product_id else None,
            )
        return super()._extract_product(html, page_url)

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
