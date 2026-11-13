"""Bridge the standalone parser's list[Item] into website search."""
import asyncio
from collections import OrderedDict
from importlib import import_module
import time
from weakref import WeakKeyDictionary
from .regions import current_region

CACHE_SECONDS = 30
MAX_CACHED_QUERIES = 16
MAX_PENDING_QUERIES = 8
_cache = OrderedDict()
_loops = WeakKeyDictionary()


def _parse_items(query: str) -> list:
    module = import_module('.wb_parse_search_phrase-master.main', package=__package__)
    return module.parse(search_phrase=query)


async def fetch_items(query: str, limit: int = 200) -> list:
    """Coalesce duplicate requests and run one parser at a time per event loop."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError('limit must be between 1 and 200')
    query = query.strip()
    if not query:
        raise ValueError('query must not be empty')
    region = current_region()
    key = (query.casefold(), region['id'] if region else None)
    now = time.monotonic()
    for old_key, (expires, _) in list(_cache.items()):
        if expires <= now:
            del _cache[old_key]
    if key in _cache:
        _cache.move_to_end(key)
        return list(_cache[key][1][:limit])
    loop = asyncio.get_running_loop()
    state = _loops.setdefault(loop, {'pending': {}, 'semaphore': asyncio.Semaphore(1)})
    if key not in state['pending']:
        if len(state['pending']) >= MAX_PENDING_QUERIES:
            raise RuntimeError('WB parser is busy; retry later')
        async def run():
            async with state['semaphore']:
                return tuple((await asyncio.to_thread(_parse_items, query))[:200])
        task = asyncio.create_task(run())
        state['pending'][key] = task
        def completed(done):
            state['pending'].pop(key, None)
            if not state['pending']:
                _loops.pop(loop, None)
            if done.cancelled() or done.exception() is not None:
                return
            _cache[key] = (time.monotonic() + CACHE_SECONDS, done.result())
            _cache.move_to_end(key)
            while len(_cache) > MAX_CACHED_QUERIES:
                _cache.popitem(last=False)
        task.add_done_callback(completed)
    # A timed-out HTTP request must not cancel a parser already running in a thread.
    items = await asyncio.shield(state['pending'][key])
    return list(items[:limit])
