from .embedded_state import extract_ozon_embedded
from .public_html import PublicHtmlSearchAdapter


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

    @classmethod
    def from_env(cls):
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
