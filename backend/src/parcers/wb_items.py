"""Return your parsed WB Item objects here; no conversion or JSON is needed."""


async def fetch_items(query: str, limit: int = 200) -> list:
    """Replace the empty list with your parser's list[Item].

    query is the website search text. Top-level Item prices must be in rubles.
    For a synchronous parser use: await asyncio.to_thread(parse, query).
    Do not return print(items), str(items), or the textual Item repr.
    """
    items = []  # Return the result of your parser here.
    return items[:min(limit, 200)]
