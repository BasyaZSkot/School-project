"""City preferences and request-local region handling.

City identifiers: https://yandex.ru/dev/tasks-api/doc/ru/regions
"""
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_CITIES = [
    (213, "Москва"), (2, "Санкт-Петербург"), (54, "Екатеринбург"),
    (43, "Казань"), (65, "Новосибирск"), (47, "Нижний Новгород"),
    (20, "Архангельск"), (37, "Астрахань"), (197, "Барнаул"), (4, "Белгород"),
    (77, "Благовещенск"), (191, "Брянск"), (24, "Великий Новгород"),
    (75, "Владивосток"), (33, "Владикавказ"), (192, "Владимир"),
    (38, "Волгоград"), (21, "Вологда"), (193, "Воронеж"), (1106, "Грозный"),
    (5, "Иваново"), (63, "Иркутск"), (41, "Йошкар-Ола"), (22, "Калининград"),
    (64, "Кемерово"), (7, "Кострома"), (35, "Краснодар"), (62, "Красноярск"),
    (53, "Курган"), (8, "Курск"), (9, "Липецк"), (28, "Махачкала"),
    (23, "Мурманск"), (1092, "Назрань"), (30, "Нальчик"), (66, "Омск"),
    (10, "Орёл"), (48, "Оренбург"), (49, "Пенза"), (50, "Пермь"), (25, "Псков"),
    (39, "Ростов-на-Дону"), (11, "Рязань"), (51, "Самара"), (42, "Саранск"),
    (12, "Смоленск"), (239, "Сочи"), (36, "Ставрополь"), (973, "Сургут"),
    (13, "Тамбов"), (14, "Тверь"), (67, "Томск"), (15, "Тула"),
    (195, "Ульяновск"), (172, "Уфа"), (76, "Хабаровск"), (45, "Чебоксары"),
    (56, "Челябинск"), (1104, "Черкесск"), (16, "Ярославль"),
]
REGIONS = [{"id": key, "name": name} for key, name in _CITIES]
_BY_ID = {r["id"]: r for r in REGIONS}
_CURRENT = ContextVar("multimarket_region", default=None)


def get_region(region_id):
    if region_id is None:
        return None
    if isinstance(region_id, bool) or region_id not in _BY_ID:
        raise ValueError("Выберите город из списка доступных регионов")
    return _BY_ID[region_id]


def current_region():
    return _CURRENT.get()


@contextmanager
def region_scope(region_id):
    token = _CURRENT.set(get_region(region_id))
    try:
        yield _CURRENT.get()
    finally:
        _CURRENT.reset(token)


def regional_url(url):
    region = current_region()
    parsed = urlparse(url)
    if not region or parsed.hostname not in {"market.yandex.ru", "www.market.yandex.ru"}:
        return url
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "lr"]
    query.append(("lr", str(region["id"])))
    return urlunparse(parsed._replace(query=urlencode(query)))


def regional_delivery(delivery):
    """Never relabel the marketplace's default-city dates as the chosen city's."""
    region = current_region()
    if region is None:
        return delivery
    source = dict(delivery or {})
    actual_id = source.get("region_id")
    normalize = lambda s: str(s or "").casefold().replace("ё", "е").strip()
    confirmed = (str(actual_id) == str(region["id"]) if actual_id is not None
                 else normalize(source.get("destination")) == normalize(region["name"]))
    if confirmed:
        source.update(requested_region_id=region["id"], region_confirmed=True)
        return source
    return {"text": "Площадка не подтвердила срок для выбранного города",
            "destination": region["name"], "requested_region_id": region["id"],
            "region_confirmed": False, "source_destination": source.get("destination")}
