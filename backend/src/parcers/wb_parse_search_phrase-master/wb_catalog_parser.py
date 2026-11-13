import asyncio
from typing import List

import httpx
from loguru import logger

if __package__:
    from .common_data import HEADERS
else:
    from common_data import HEADERS
if __package__:
    from .dto import DataPage
else:
    from dto import DataPage


class WbCatalogAsyncFetcher:

    def __init__(self,
                 search_phrase: str,
                 cookies: dict,
                 pages: List[DataPage] | None = None,
                 batch_size: int = 50,
                 max_concurrent: int = 50,
                 timeout: int = 10,
                 max_retries: int = 4,
                 pause_between_batches: float = 1
                 ):
        self.pages = pages  # Kept for callers; price ranges are not used in limited mode.
        self.search_phrase = search_phrase
        self.cookies = cookies
        self.headers = HEADERS

        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = timeout
        self.max_retries = max_retries
        self.pause_between_batches = pause_between_batches

    def _build_task(self) -> list[dict]:
        # WB returns 100 products per page; only the first 200 are needed.
        tasks = [{"page": page} for page in range(1, 3)]
        logger.info(f"Сформировано задач: {len(tasks)}")
        return tasks

    def _build_params(self, task: dict) -> dict:
        return {
            'ab_testid': 'promo_mask_test_1',
            'appType': '1',
            'autoselectFilters': 'false',
            'curr': 'rub',
            'dest': '-1275551',
            'hide_dtype': '9',
            'hide_vflags': '4294967296',
            'inheritFilters': 'false',
            'lang': 'ru',
            'page': str(task["page"]),
            'sort': 'popular',
            'query': self.search_phrase,
            'resultset': 'catalog',
            'spp': '30',
            'suppressSpellcheck': 'false',
        }

    async def _fetch_one(self,
                         client: httpx.AsyncClient,
                         task: dict) -> dict | None:
        params = self._build_params(task=task)

        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.semaphore:
                    response = await client.get(
                        'https://www.wildberries.ru/__internal/u-search/exactmatch/ru/common/v18/search',
                        params=params,
                        cookies=self.cookies,
                        headers=self.headers,
                        timeout=self.timeout,
                    )
                    if response.status_code == 200:
                        logger.debug(
                            f"✅ page={task['page']} "

                        )
                        return response.json()

                logger.warning(
                    f"⚠ status={response.status_code} "
                    f"page={task['page']} attempt={attempt}"
                )
            except httpx.RequestError as err:
                logger.error(err)

            await asyncio.sleep(0.5 * attempt)

        logger.error(
            f"❌ failed page={task['page']} "

        )
        return None


    async def fetch_all(self) -> list[dict]:
        tasks = self._build_task()
        results: list[dict] = []
        seen = set()
        count = 0

        async with httpx.AsyncClient() as client:
            for i in range(0, len(tasks), self.batch_size):
                batch = tasks[i: i + self.batch_size]

                logger.info(
                    f"Батч {i // self.batch_size + 1} "
                    f"({len(batch)} запросов)"
                )

                coroutines = [
                    self._fetch_one(client, task) for task in batch
                ]

                batch_results = await asyncio.gather(*coroutines)
                batch_results = [r for r in batch_results if r]

                for payload in batch_results:
                    products = payload.get("products")
                    if not isinstance(products, list):
                        products = (payload.get("data") or {}).get("products", [])
                    selected = []
                    for product in products:
                        if not isinstance(product, dict) or product.get("id") is None:
                            continue
                        sku = str(product["id"])
                        if sku in seen:
                            continue
                        seen.add(sku)
                        selected.append(product)
                        count += 1
                        if count >= 200:
                            break
                    results.append({**payload, "products": selected})
                    if count >= 200:
                        break
                if count >= 200:
                    break

                logger.success(
                    f"✅ Батч завершён, всего ответов: {len(results)}"
                )

                if i + self.batch_size < len(tasks):
                    await asyncio.sleep(self.pause_between_batches)

        logger.info(f"Готово. Всего ответов: {len(results)}")
        return results
