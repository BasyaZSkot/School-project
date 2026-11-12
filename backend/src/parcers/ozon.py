import os

from .embedded_state import extract_ozon_embedded, extract_ozon_product
from .feed import JsonFeedAdapter
from .public_html import PublicHtmlSearchAdapter
from .product_data import image_urls


class OzonAdapter(PublicHtmlSearchAdapter):
    """Ozon public-page connector with embedded search-state extraction."""

    marketplace = "Ozon"
    base_search_url = "https://www.ozon.ru/search/?text={query}"
    allowed_hosts = ("ozon.ru",)

    def _extract(self, html: str, page_url: str, limit: int):
        # Prefer structured tile data when it is already included in the public
        # HTML response. Never request Ozon's private JSON endpoints separately.
        offers = extract_ozon_embedded(
            html,
            page_url,
            self._valid_marketplace_url,
        )
        return offers[:limit] if offers else super()._extract(html, page_url, limit)

    def _extract_product(self, html: str, page_url: str):
        embedded = extract_ozon_product(html, page_url)
        structured = super()._extract_product(html, page_url)
        if embedded is None:
            return structured
        if structured is not None:
            embedded.description = embedded.description or structured.description
            embedded.rating = embedded.rating if embedded.rating is not None else structured.rating
            embedded.review_count = embedded.review_count if embedded.review_count is not None else structured.review_count
            embedded.specifications = embedded.specifications or structured.specifications
            embedded.reviews = embedded.reviews or structured.reviews
            embedded.image_url = embedded.image_url or structured.image_url
            embedded.image_urls = image_urls([embedded.image_urls, structured.image_urls])
            embedded.delivery = embedded.delivery or structured.delivery
        return embedded

    @classmethod
    def from_env(cls):
        feed_url = os.getenv("MULTIMARKET_OZON_FEED_URL", "").strip()
        if feed_url:
            return JsonFeedAdapter(
                marketplace=cls.marketplace,
                base_search_url=cls.base_search_url,
                reason="Подключён разрешённый партнёрский источник Ozon.",
                feed_url=feed_url,
                token=os.getenv("MULTIMARKET_OZON_FEED_TOKEN", "").strip() or None,
                allowed_hosts=cls.allowed_hosts,
            )
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
