"""Product identity is independent of the marketplace and seller."""
import re
from .variants import COLORS, norm

NOISE = set('наушники беспроводные проводные с микрофоном смартфон телефон мобильный кроссовки кеды форсы обувь headphones wireless smartphone оригинал оригинальные оригинальный новый новое new восстановленный восстановлен refurbished refurb витринный образец уцененный уценка used бу'.split())
BRANDS = {'эппл': 'apple', 'самсунг': 'samsung', 'сяоми': 'xiaomi', 'сони': 'sony', 'найк': 'nike'}
SPEC_ALIASES = {
    'размер обуви': 'size', 'размер одежды': 'size', 'размер': 'size', 'size': 'size',
    'пол': 'gender', 'gender': 'gender', 'процессор': 'processor', 'модель процессора': 'processor',
    'диагональ экрана': 'screen', 'диагональ': 'screen', 'screen size': 'screen',
    'разрешение экрана': 'resolution', 'емкость аккумулятора': 'battery', 'емкость батареи': 'battery',
    'количество sim карт': 'sim_count', 'число sim карт': 'sim_count',
    'материал': 'material', 'материал верха': 'upper_material', 'состав': 'composition',
    'мощность': 'power', 'объем': 'volume', 'вес': 'weight', 'масса': 'weight',
    'артикул производителя': 'manufacturer_code', 'код производителя': 'manufacturer_code',
}
NON_IDENTITY = {'продавец', 'магазин', 'рейтинг', 'оценка', 'количество отзывов', 'отзывы', 'цена', 'доставка', 'срок доставки', 'наличие', 'артикул', 'артикул wb', 'артикул wildberries', 'артикул маркета', 'страна производства', 'страна производитель', 'гарантия', 'гарантийный срок', 'описание'}


def brand_name(value):
    value = norm(value)
    return BRANDS.get(value, value)


def spec_value(value):
    text = str(value).casefold().replace('ё', 'е')
    text = re.sub(r'(?<=\d),(?=\d)', '.', text)
    text = text.replace('mah', 'мач').replace('мaч', 'мач').replace('мм', 'mm').replace('кг', 'kg')
    return re.sub(r'\s+', '', text).strip()


def constraints(offer):
    result = dict(offer.variants)
    for spec in offer.specifications:
        name = norm(spec.get('name'))
        key = SPEC_ALIASES.get(name) or ('spec:' + name if name and name not in NON_IDENTITY else None)
        if name in {'цвет', 'цвет товара', 'color', 'бренд', 'модель', 'комплектация', 'состояние', 'версия', 'оперативная память', 'объем встроенной памяти', 'встроенная память'}:
            continue  # Canonical fields/variants already cover these aliases.
        if key and spec.get('value'):
            result[key] = spec_value(spec.get('value'))
    return result


def model_key(offer):
    # Keep model modifiers (Pro/Max/Plus/SE); seller names are never consulted.
    text = str(offer.model or offer.title).casefold()
    text = re.sub(r'\b\d{1,3}\s*[/+]\s*\d{2,4}\s*(?:гб|gb)\b', ' ', text)
    text = re.sub(r'\b\d+(?:[.,]\d+)?\s*(?:гб|gb|тб|tb)\b', ' ', text)
    text = norm(text)
    brand = brand_name(offer.brand)
    words = [BRANDS.get(word, word) for word in text.split()]
    brand_words = set(brand.split()) | set(BRANDS.values()) | {'huawei', 'honor', 'realme', 'dyson', 'adidas', 'lenovo', 'asus', 'jbl'}
    words = [word for word in words if word not in NOISE and word not in COLORS and word not in brand_words]
    # Split punctuation/alphanumeric model spelling consistently (WH-1000XM5 / WH1000XM5).
    tokens = re.findall(r'[a-zа-я]+|\d+', ' '.join(words))
    if not any(token.isalpha() for token in tokens) or not (any(token.isdigit() for token in tokens) or brand and len(tokens) >= 2):
        return None
    return tuple(sorted(tokens))


def compatible(left, right):
    a, b = constraints(left), constraints(right)
    if any(a[key] != b[key] for key in a.keys() & b.keys()):
        return False
    # Unlabelled listings must not absorb used, display or refurbished units.
    if a.get('size') != b.get('size'):
        return False
    if a.get('condition') != b.get('condition') and any(state not in (None, 'новый') for state in (a.get('condition'), b.get('condition'))):
        return False
    if left.brand and right.brand and brand_name(left.brand) != brand_name(right.brand):
        return False
    a = re.sub(r'\D', '', str(left.gtin or ''))
    b = re.sub(r'\D', '', str(right.gtin or ''))
    if len(a) in {8, 12, 13, 14} and len(b) in {8, 12, 13, 14} and a != b:
        return False
    return True
