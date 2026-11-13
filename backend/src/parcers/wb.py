from . import wb_requests
import os
import re

from .embedded_state import extract_wildberries_embedded
from .feed import JsonFeedAdapter
from .public_html import PublicHtmlSearchAdapter
from .wb_adapter import wb_record_to_offer


class WildberriesAdapter(PublicHtmlSearchAdapter):
    """Wildberries public-page connector with embedded catalog extraction."""

    async def _fetch_public_page(self, url: str) -> tuple[str, str]:
        return await wb_requests.fetch_public_page(url, self._valid_marketplace_url, self._fetcher)

    marketplace = "Wildberries"
    base_search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
    allowed_hosts = ("wildberries.ru", "wildberries.by", "wildberries.kz")

    def _extract(self, html: str, page_url: str, limit: int):
        # Parse a products[] payload only when the public page itself contains
        # it. No internal search endpoint or browser session is used.
        offers = extract_wildberries_embedded(html, limit)
        return offers if offers else super()._extract(html, page_url, limit)

    def _extract_product(self, html: str, page_url: str):
        product_id = re.search(r"/catalog/(\d+)(?:/|$)", page_url)
        embedded = None
        if product_id:
            embedded = next(
                (offer for offer in extract_wildberries_embedded(html, 50)
                 if offer.external_id == product_id.group(1)),
                None,
            )
        structured = super()._extract_product(html, page_url)
        if embedded is None:
            return structured
        if structured is not None:
            embedded.description = structured.description
            embedded.rating = structured.rating
            embedded.review_count = structured.review_count
            embedded.specifications = embedded.specifications or structured.specifications
            embedded.reviews = embedded.reviews or structured.reviews
            embedded.image_url = embedded.image_url or structured.image_url
        return embedded

    @classmethod
    def from_env(cls):
        if os.getenv("MULTIMARKET_WB_SOURCE", "").strip().lower() == "items":
            from . import wb_items
            from .wb_adapter import WildberriesAdapter as ItemsAdapter
            return ItemsAdapter.from_record_source(wb_items.fetch_items, prices_in_rubles=True)
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
