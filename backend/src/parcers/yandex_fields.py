"""Normalize fields published in each Yandex search snippet, without extra requests."""
import json
import math
from .product_data import image_urls
from .variants import extract, norm


def public_json(value):
    if not isinstance(value, str) or len(value) > 60000:
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).replace(',', '.'))
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError):
        return None


def label(value):
    return value.strip()[:200] if isinstance(value, str) and value.strip() else None


def apply_fields(offer, metadata=None, vendors=None, images=None):
    data = metadata or {}
    # Metadata is scoped by the enclosing searchOrganic card. marketSku may
    # identify a seller offer and legitimately differ from the public card ID.
    offer.brand = offer.brand or label(data.get('vendorName')) or label(data.get('brandName')) or (vendors or {}).get(str(data.get('vendorId')))
    offer.model = offer.model or label(data.get('modelName'))
    for spec in offer.specifications:
        name, value = norm(spec.get('name')), label(spec.get('value'))
        if name in {'бренд', 'производитель', 'brand'}:
            offer.brand = offer.brand or value
        elif name in {'модель', 'линейка', 'model'}:
            offer.model = offer.model or value
    signals = data.get('signals') if isinstance(data.get('signals'), list) else []
    offer.seller = offer.seller or label(data.get('shopName')) or next((label(s.get('title')) for s in signals if isinstance(s, dict) and s.get('type') == 'shop' and label(s.get('title'))), None)
    rating = data.get('rating') if isinstance(data.get('rating'), dict) else {}
    if rating.get('ratingType') in (None, 'product'):
        score = number(rating.get('rating'))
        count = number(rating.get('gradesCount'))
        if offer.rating is None and score is not None and 0 < score <= 5:
            offer.rating = score
        if offer.review_count is None and count is not None and count >= 0 and count.is_integer():
            offer.review_count = int(count)
    stock = data.get('lastStock') if isinstance(data.get('lastStock'), dict) else {}
    quantity = number(stock.get('stockItemCount'))
    if offer.in_stock is None and quantity is not None and quantity >= 0:
        offer.in_stock = quantity > 0
    # Base price is unconditional; additionalPrices may require a bank card/subscription.
    price = number(data.get('price'))
    if price is not None and price > 0:
        offer.price = price
    offer.image_urls = image_urls([offer.image_url, offer.image_urls, images or []], offer.url)
    offer.image_url = next(iter(offer.image_urls), None)
    offer.variants = extract(offer.title, offer.specifications, offer.variants, offer.brand, offer.model, offer.condition)
    return offer
