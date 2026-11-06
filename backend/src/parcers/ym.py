from .public_html import PublicHtmlSearchAdapter


class YandexMarketAdapter(PublicHtmlSearchAdapter):
    """Yandex Market public-page connector."""

    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"
    allowed_hosts = ("market.yandex.ru",)

    @classmethod
    def from_env(cls):
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
