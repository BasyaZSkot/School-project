"""Independent public-page request entry point for OZON."""
from .regions import current_region, regional_url
from .transport import FetcherConfig, ResilientFetcher

_fetchers = {}


def get_fetcher():
    region = current_region()
    key = region["id"] if region else None
    fetcher = _fetchers.pop(key, None)
    if fetcher is None:
        fetcher = ResilientFetcher(FetcherConfig.from_env())
    _fetchers[key] = fetcher
    if len(_fetchers) > 8:
        del _fetchers[next(iter(_fetchers))]
    return fetcher


async def fetch_public_page(url, validate_url, fetcher=None):
    url = regional_url(url)
    page = await (fetcher if fetcher is not None else get_fetcher()).fetch(url)
    if not validate_url(page.url, url):
        raise ValueError("Marketplace redirected outside its own domain")
    return page.url, page.text
