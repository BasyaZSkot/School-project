from .base import DisabledAdapter, SearchStatus


class WildberriesAdapter(DisabledAdapter):
    marketplace = "Wildberries"
    base_search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
    status = SearchStatus.ACCESS_REQUIRED
    reason = (
        "Внутренний endpoint из исследовательской заметки не считается стабильным "
        "публичным API для сторонних агрегаторов. Нужен разрешённый партнёрский "
        "источник данных или письменное разрешение."
    )
