from .public_html import PublicHtmlSearchAdapter


class OzonAdapter:
    marketplace = "Ozon"
    base_search_url = "https://www.ozon.ru/search/?text={query}"

    @classmethod
    def from_env(cls):
        return PublicHtmlSearchAdapter(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=("ozon.ru",),
        )
