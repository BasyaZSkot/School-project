import os

from .base import DisabledAdapter, SearchStatus
from .feed import JsonFeedAdapter
from .wb_adapter import WildberriesAdapter as _RecordAdapter


class WildberriesAdapter(DisabledAdapter):
    marketplace = "Wildberries"
    base_search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
    status = SearchStatus.ACCESS_REQUIRED
    reason = (
        "Для автоматической выдачи нужен разрешённый API, лицензированный фид "
        "или письменное разрешение. Пока доступна прямая ссылка на поиск."
    )

    @classmethod
    def from_env(cls):
        url = os.getenv("MULTIMARKET_WB_FEED_URL")
        if not url:
            return cls()
        return JsonFeedAdapter(
            marketplace=cls.marketplace,
            base_search_url=cls.base_search_url,
            reason=cls.reason,
            feed_url=url,
            token=os.getenv("MULTIMARKET_WB_FEED_TOKEN"),
        )

    @classmethod
    def from_record_source(cls, source):
        """Use an approved async source returning records from the WB example model."""
        return _RecordAdapter(source=source)
