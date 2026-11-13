"""Additional exact model matching across different marketplace title formats."""
import json
import re
from .variants import COLORS, norm

# Category/advertising words add no model identity. Remaining words are retained.
NOISE = set('наушники беспроводные проводные с микрофоном смартфон телефон мобильный кроссовки кеды форсы обувь headphones wireless smartphone оригинал оригинальные оригинальный'.split())


def constraints(offer):
    result = dict(offer.variants)
    for spec in offer.specifications:
        name = norm(spec.get('name'))
        if name in {'размер', 'размер обуви', 'размер одежды', 'size', 'пол', 'gender'}:
            result['gender' if name in {'пол', 'gender'} else 'size'] = norm(spec.get('value'))
    return result


def model_key(offer):
    brand = norm(offer.brand)
    if not brand:
        return None
    text = norm(offer.model or offer.title)
    text = re.sub(r'\b\d+(?:\s+\d+)?\s*(?:гб|gb|тб|tb)\b', ' ', text)
    words = [word for word in text.split() if word not in NOISE and word not in COLORS and word not in brand.split()]
    # Split punctuation/alphanumeric model spelling consistently (WH-1000XM5 / WH1000XM5).
    tokens = re.findall(r'[a-zа-я]+|\d+', ' '.join(words))
    if not any(token.isdigit() for token in tokens) or not any(token.isalpha() for token in tokens):
        return None
    return (brand, tuple(tokens), json.dumps(constraints(offer), ensure_ascii=False, sort_keys=True))


def compatible(left, right):
    if constraints(left) != constraints(right):
        return False
    if left.brand and right.brand and norm(left.brand) != norm(right.brand):
        return False
    a = re.sub(r'\D', '', str(left.gtin or ''))
    b = re.sub(r'\D', '', str(right.gtin or ''))
    if len(a) in {8, 12, 13, 14} and len(b) in {8, 12, 13, 14} and a != b:
        return False
    return True
