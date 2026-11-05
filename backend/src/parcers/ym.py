from .public_html import PublicHtmlSearchAdapter


class YandexMarketAdapter:
    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"

    @classmethod
    def from_env(cls):
        return PublicHtmlSearchAdapter(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=("market.yandex.ru",),
        )
