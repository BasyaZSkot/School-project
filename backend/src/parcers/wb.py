from .public_html import PublicHtmlSearchAdapter


class WildberriesAdapter(PublicHtmlSearchAdapter):
    """Wildberries public-page connector with its own host and URL policy."""

    marketplace = "Wildberries"
    base_search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
    allowed_hosts = ("wildberries.ru", "wildberries.by", "wildberries.kz")

    @classmethod
    def from_env(cls):
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
