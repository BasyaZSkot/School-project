"""Bridge the standalone parser's list[Item] into website search."""
import asyncio
from importlib import import_module


def _parse_items(query: str) -> list:
    module = import_module('.wb_parse_search_phrase-master.main', package=__package__)
    return module.parse(search_phrase=query)


async def fetch_items(query: str, limit: int = 200) -> list:
    """Run the synchronous parser outside the server event loop."""
    items = await asyncio.to_thread(_parse_items, query)
    return items[:min(limit, 200)]
