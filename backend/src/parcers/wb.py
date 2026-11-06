from .embedded_state import extract_wildberries_embedded
from .public_html import PublicHtmlSearchAdapter


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
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
