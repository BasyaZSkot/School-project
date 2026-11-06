import os

from .embedded_state import extract_wildberries_embedded
from .feed import JsonFeedAdapter
from .public_html import PublicHtmlSearchAdapter
from .wb_adapter import wb_record_to_offer


class WildberriesAdapter(PublicHtmlSearchAdapter):
    """Wildberries public-page connector with embedded catalog extraction."""

    marketplace = "Wildberries"
    base_search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
    allowed_hosts = ("wildberries.ru", "wildberries.by", "wildberries.kz")

    def _extract(self, html: str, page_url: str, limit: int):
        # Parse a products[] payload only when the public page itself contains
        # it. No internal search endpoint or browser session is used.
        offers = extract_wildberries_embedded(html, limit)
        return offers if offers else super()._extract(html, page_url, limit)

    @classmethod
    def from_env(cls):
        feed_url = os.getenv("MULTIMARKET_WB_FEED_URL", "").strip()
        if feed_url:
            feed_format = os.getenv("MULTIMARKET_WB_FEED_FORMAT", "").strip().lower()
            if feed_format not in {"", "offers", "wb_records"}:
                raise ValueError(
                    "MULTIMARKET_WB_FEED_FORMAT must be 'offers' or 'wb_records'"
                )
            wb_records = feed_format == "wb_records"
            return JsonFeedAdapter(
                marketplace=cls.marketplace,
                base_search_url=cls.base_search_url,
                reason="Подключён разрешённый партнёрский источник Wildberries.",
                feed_url=feed_url,
                token=os.getenv("MULTIMARKET_WB_FEED_TOKEN", "").strip() or None,
                records_key="products" if wb_records else "offers",
                record_mapper=wb_record_to_offer if wb_records else None,
                allowed_hosts=cls.allowed_hosts,
            )
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
