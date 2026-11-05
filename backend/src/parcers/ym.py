from .base import DisabledAdapter, SearchStatus


class YandexMarketAdapter(DisabledAdapter):
    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"
    status = SearchStatus.POLICY_RESTRICTED
    reason = (
        "Автоматизированный доступ без предусмотренной авторизации не включён. "
        "Для интеграции нужен согласованный API/партнёрский источник и соблюдение "
        "его лицензионных условий."
    )
