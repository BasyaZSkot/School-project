from .public_html import PublicHtmlSearchAdapter


class OzonAdapter(PublicHtmlSearchAdapter):
    """Ozon public-page connector; isolated so Ozon-specific parsing can evolve."""

    marketplace = "Ozon"
    base_search_url = "https://www.ozon.ru/search/?text={query}"
    allowed_hosts = ("ozon.ru",)

    @classmethod
    def from_env(cls):
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
