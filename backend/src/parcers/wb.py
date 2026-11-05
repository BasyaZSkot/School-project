from .public_html import PublicHtmlSearchAdapter


class WildberriesAdapter:
    marketplace = "Wildberries"
    base_search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"

    @classmethod
    def from_env(cls):
        return PublicHtmlSearchAdapter(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=("wildberries.ru", "wildberries.by", "wildberries.kz"),
        )
