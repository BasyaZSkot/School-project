"""Fixed-host public WB images and product attributes, without price guesses."""
import asyncio
from collections import OrderedDict
from importlib import import_module
import re
import time

import httpx

routes = import_module('.wb_parse_search_phrase-master.calc_basket', package=__package__)
_cards = OrderedDict()


def product_id(url):
    match = re.search(r'/catalog/([1-9]\d{0,14})/detail\.aspx(?:[?#]|$)', url)
    return int(match[1]) if match else None


def media_base(sku):
    if type(sku) is not int or not 1 <= sku <= 999_999_999_999_999:
        raise ValueError('Invalid WB product ID')
    return f'https://{routes.basket_host(sku // 100000)}/vol{sku // 100000}/part{sku // 1000}/{sku}'


def image_url(sku, index=1):
    if type(index) is not int or not 1 <= index <= 20:
        raise ValueError('Invalid image index')
    return f'{media_base(sku)}/images/big/{index}.webp'


def attributes(data, sku, base):
    if not isinstance(data, dict) or str(data.get('nm_id')) != str(sku):
        return None
    specs = []
    options = data.get('options')
    for item in (options if isinstance(options, list) else [])[:99]:
        if isinstance(item, dict) and item.get('name') and item.get('value'):
            specs.append({'name': str(item['name'])[:160], 'value': str(item['value'])[:500]})
    photo_data = data.get('media')
    count = photo_data.get('photo_count', 0) if isinstance(photo_data, dict) else 0
    count = min(count, 20) if type(count) is int and count > 0 else 0
    result = {'details_available': True, 'metadata_only': True, 'specifications': specs}
    if data.get('description'):
        result['description'] = str(data['description'])[:5000]
    if data.get('vendor_code'):
        specs.append({'name': 'Артикул производителя', 'value': str(data['vendor_code'])[:160]})
    if count:
        result['image_urls'] = [f'{base}/images/big/{i}.webp' for i in range(1, count + 1)]
        result['image_url'] = result['image_urls'][0]
    return result


async def product_attributes(url):
    sku = product_id(url)
    if sku is None:
        return None
    cached = _cards.get(sku)
    if cached and cached[0] > time.monotonic():
        _cards.move_to_end(sku)
        return cached[1]
    try:
        base = await asyncio.to_thread(media_base, sku)
        async with httpx.AsyncClient(timeout=4, follow_redirects=False) as client:
            async with client.stream('GET', base + '/info/ru/card.json') as response:
                response.raise_for_status()
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 1_000_000:
                        return None
        import json
        result = attributes(json.loads(chunks), sku, base)
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
        result = None
    _cards[sku] = (time.monotonic() + (300 if result else 30), result)
    _cards.move_to_end(sku)
    while len(_cards) > 128:
        _cards.popitem(last=False)
    return result
