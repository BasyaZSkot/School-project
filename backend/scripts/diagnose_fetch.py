"""Show how each marketplace answers from THIS machine.

Sends one plain request per marketplace (and per proxy from
MULTIMARKET_PROXY_URLS, if set) with no retries and no parsing, and prints
what came back. Use it to tell apart: no response at all (region/IP), an
anti-bot answer (403/498/429/challenge), or a normal page without products.

    python backend/scripts/diagnose_fetch.py "наушники"
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

import os  # noqa: E402

from src.parcers.ozon import OzonAdapter  # noqa: E402
from src.parcers.transport import (  # noqa: E402
    browser_profiles,
    looks_like_challenge,
    make_client_factory,
    parse_proxy_urls,
)
from src.parcers.wb import WildberriesAdapter  # noqa: E402
from src.parcers.ym import YandexMarketAdapter  # noqa: E402

TARGETS = {
    "Ozon": OzonAdapter.base_search_url,
    "Wildberries": WildberriesAdapter.base_search_url,
    "Yandex Market": YandexMarketAdapter.base_search_url,
}


def verdict(status: int, text: str) -> str:
    if status in (401, 403, 429, 498):
        return "антибот/ограничение доступа: сайт ответил, но не пускает запрос"
    if status >= 400:
        return "ошибка сервера или страницы"
    if looks_like_challenge(text):
        return "страница проверки (капча/антибот) с кодом 200"
    if "ld+json" not in text:
        return "страница пришла, но без JSON-LD: данные подгружаются скриптом"
    return "нормальная страница с разметкой товаров"


async def probe(factory, name: str, url: str, proxy: str | None, mode: str) -> None:
    route = (urlparse(proxy).hostname if proxy else "direct") + mode
    headers = browser_profiles()[0]
    started = time.monotonic()
    try:
        async with factory(proxy, headers, None, 15.0) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        took = time.monotonic() - started
        print(f"[{name} | {route}] НЕТ ОТВЕТА за {took:.1f}s ({type(exc).__name__}).")
        print("    Сайт молча не отвечает: чаще всего блокировка по региону/IP. Попробуйте RU-прокси.")
        return
    except httpx.RequestError as exc:
        print(f"[{name} | {route}] сетевая ошибка: {type(exc).__name__}: {exc}")
        return
    took = time.monotonic() - started
    text = response.text
    snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()[:160]
    print(
        f"[{name} | {route}] HTTP {response.status_code} за {took:.1f}s, "
        f"{len(text)} симв., server={response.headers.get('server', '-')}, "
        f"итоговый хост={urlparse(str(response.url)).hostname}"
    )
    print(f"    {verdict(response.status_code, text)}")
    if snippet:
        print(f"    начало текста: {snippet}")


async def main() -> None:
    query = " ".join(sys.argv[1:]) or "наушники"
    proxies = parse_proxy_urls(os.getenv("MULTIMARKET_PROXY_URLS", ""))
    impersonate = os.getenv("MULTIMARKET_IMPERSONATE", "").strip() or None
    factory = make_client_factory(impersonate)
    mode = f" +{impersonate}" if impersonate else ""
    routes = [None, *proxies]
    print(f"Запрос: {query!r}; маршрутов: {len(routes)} (direct + {len(proxies)} прокси){mode}\n")
    for name, template in TARGETS.items():
        url = template.format(query=quote_plus(query))
        for proxy in routes:
            await probe(factory, name, url, proxy, mode)
        print()


if __name__ == "__main__":
    asyncio.run(main())
