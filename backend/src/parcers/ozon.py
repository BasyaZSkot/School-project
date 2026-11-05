from .base import DisabledAdapter, SearchStatus


class OzonAdapter(DisabledAdapter):
    marketplace = "Ozon"
    base_search_url = "https://www.ozon.ru/search/?text={query}"
    status = SearchStatus.POLICY_RESTRICTED
    reason = (
        "Автоматический сбор с ozon.ru и его внутренних API не включён: "
        "публичный Seller API не является анонимным поиском каталога для покупателей. "
        "Подключение возможно после получения разрешённого источника данных."
    )
