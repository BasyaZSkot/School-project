import os

from .base import DisabledAdapter, SearchStatus
from .feed import JsonFeedAdapter


class OzonAdapter(DisabledAdapter):
    marketplace = "Ozon"
    base_search_url = "https://www.ozon.ru/search/?text={query}"
    status = SearchStatus.POLICY_RESTRICTED
    reason = (
        "Автоматический сбор с ozon.ru и его внутренних API не включён. "
        "Подключите разрешённый API или лицензированный партнёрский фид."
    )

    @classmethod
    def from_env(cls):
        url = os.getenv("MULTIMARKET_OZON_FEED_URL")
        if not url:
            return cls()
        return JsonFeedAdapter(
            marketplace=cls.marketplace,
            base_search_url=cls.base_search_url,
            reason=cls.reason,
            feed_url=url,
            token=os.getenv("MULTIMARKET_OZON_FEED_TOKEN"),
        )
