"""Public WB media routes, shared by standalone parsing and the website."""
import json
from pathlib import Path
import re
from threading import Lock
import time
from urllib.request import urlopen

REGISTRY_URL = 'https://cdn.wbbasket.ru/api/v3/upstreams'
_lock = Lock()
_expires = 0


def validate_routes(routes):
    result = []
    for entry in routes:
        lo, hi, host = entry['vol_range_from'], entry['vol_range_to'], entry['host']
        if type(lo) is not int or type(hi) is not int or not 0 <= lo <= hi or not re.fullmatch(r'basket-\d{2,3}\.wbbasket\.ru', host):
            raise ValueError('Invalid WB media route')
        result.append((lo, hi, host))
    result.sort()
    if not result or result[0][0] != 0 or any(a[1] + 1 != b[0] for a, b in zip(result, result[1:])):
        raise ValueError('Incomplete WB media routes')
    return result


_routes = validate_routes(json.loads(Path(__file__).with_name('media_routes.json').read_text(encoding='utf-8')))


def basket_host(short_id: int) -> str:
    global _routes, _expires
    if type(short_id) is not int or short_id < 0:
        raise ValueError('Invalid WB volume')
    if time.monotonic() >= _expires:
        with _lock:
            if time.monotonic() >= _expires:
                try:
                    with urlopen(REGISTRY_URL, timeout=3) as response:
                        raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise ValueError('WB registry is too large')
                    data = json.loads(raw)
                    hosts = [host for route in data['origin']['mediabasket_route_map'] if route['method'] == 'range' for host in route['hosts']]
                    updated = validate_routes(hosts)
                    if updated[-1][1] < _routes[-1][1]:
                        raise ValueError('Truncated WB registry')
                    _routes = updated
                    _expires = time.monotonic() + 3600
                except (OSError, ValueError, KeyError, TypeError):
                    # Keep the bundled/last good routing table during outages.
                    _expires = time.monotonic() + 60
    for lo, hi, host in _routes:
        if lo <= short_id <= hi:
            return host
    raise ValueError('Unknown WB media volume')

def calc_numb_basket(short_id: int) -> str:
    return basket_host(short_id).split('.')[0].removeprefix('basket-')
