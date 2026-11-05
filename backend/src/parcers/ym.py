import os

from .base import DisabledAdapter, SearchStatus
from .feed import JsonFeedAdapter


class YandexMarketAdapter(DisabledAdapter):
    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"
    status = SearchStatus.POLICY_RESTRICTED
    reason = (
        "Для автоматизированной выдачи нужен согласованный API или "
        "лицензированный партнёрский источник данных."
    )

    @classmethod
    def from_env(cls):
        url = os.getenv("MULTIMARKET_YM_FEED_URL")
        if not url:
            return cls()
        return JsonFeedAdapter(
            marketplace=cls.marketplace,
            base_search_url=cls.base_search_url,
            reason=cls.reason,
            feed_url=url,
            token=os.getenv("MULTIMARKET_YM_FEED_TOKEN"),
        )
