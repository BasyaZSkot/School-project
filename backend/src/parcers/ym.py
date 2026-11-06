import os

from .feed import JsonFeedAdapter
from .public_html import PublicHtmlSearchAdapter


class YandexMarketAdapter(PublicHtmlSearchAdapter):
    """Yandex Market public-page connector."""

    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"
    allowed_hosts = ("market.yandex.ru",)

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
