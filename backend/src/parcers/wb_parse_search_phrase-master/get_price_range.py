
import requests
import json
from loguru import logger

from common_data import HEADERS
from dto import DataPage


class WbSearchPhraseParserRange:
    def __init__(self, search_phrase: str, cookies: dict = None):
        self.search_phrase = search_phrase
        self.cookies = cookies

        self.default_step = 5000 * 100
        self.max_count_of_good = 5000

        self.min_step = 10 * 100
        self.max_step = 50_000 * 100

        self.max_split_depth = 10
        self.low_goods_threshold = 500

    def fetch_data(self, add_params: dict = None):
        params = {
            'ab_testid': 'promo_mask_test_1',
            'appType': '1',
            'autoselectFilters': 'false',
            'curr': 'rub',
            'dest': '-1275551',
            'hide_dtype': '9',
            'hide_vflags': '4294967296',
            'inheritFilters': 'false',
            'lang': 'ru',
            #'priceU': '250000;350000',
            'query': self.search_phrase,
            'resultset': 'filters',
            'spp': '30',
            'suppressSpellcheck': 'false',
        }
        if add_params:
            params.update(add_params)

        response = requests.get('https://www.wildberries.ru/__internal/u-search/exactmatch/ru/common/v18/search',
                                params=params,
                                cookies=self.cookies,
                                headers=HEADERS)
        if response.status_code == 200:
            return response.json()

        logger.error(f"WB status: {response.status_code}")
        return None

    @staticmethod
    def _get_total(data: json):
        return data.get("data", {}).get("total")


    @staticmethod
    def _get_min_max_price(data: json)-> tuple:
        filters = data.get("data", {}).get("filters", [])

        for _filter in filters:
            if _filter.get("name") == "Цена":
                return _filter.get("minPriceU"), _filter.get("maxPriceU")
        return None, None


    def get_price_range(self, data: json) -> DataPage | None:
        if not data:
            return

        total = self._get_total(data=data)
        min_price, max_price = self._get_min_max_price(data=data)

        if not all([total, min_price, max_price]):
            return None

        return DataPage(min_price=min_price, max_price=max_price, total=total)


    def split_price_range(self, min_price, max_price, depth=0) -> list[DataPage]:
        if depth > self.max_split_depth:
            logger.warning("Превышена глубина дробления")
            return []

        if max_price - min_price <= self.min_step:
            logger.warning("Минимальный шаг достигнут")
            res = self.fetch_data(add_params={"priceU": f'{min_price};{max_price}'})
            data = self.get_price_range(res)

            return [DataPage(min_price, max_price, data.total) if data else 0]

        res = self.fetch_data(add_params={"priceU": f'{min_price};{max_price}'})
        data = self.get_price_range(res)

        if not data:
            logger.error("Нет данных")
            return []

        if data.total <= self.max_count_of_good:
            logger.info(f"ок - {data.total}")
            return [DataPage(min_price, max_price, data.total)]

        logger.warning(f"Дробим-{data.total}")

        min_rub = min_price // 100
        max_rub = max_price // 100

        if min_rub >= max_rub:
            logger.warning("Диапазон в 1 рубль, дальше дробить нельзя")
            return [DataPage(min_price, max_price, data.total)]

        mid_rub = (min_rub + max_rub) // 2
        mid = mid_rub * 100

        left = self.split_price_range(min_price=min_price, max_price=mid, depth=depth + 1)
        right = self.split_price_range(min_price=mid + 100, max_price=max_price, depth=depth + 1)

        return left + right




    def parse(self):
        logger.info(f"Начинаем парсинг <{self.search_phrase}>")

        base_data = self.get_price_range(data=self.fetch_data())
        if not base_data:
            logger.error("Не удалось получить данные")
            return

        result: list[DataPage] = []

        step = self.default_step

        start_price = base_data.min_price

        # TODO верни на место

        #while start_price < 50_000:
        while start_price < base_data.max_price:
            finish_price = min(start_price + step, base_data.max_price)

            logger.info(f"Диапазон: {start_price / 100} - {finish_price / 100}. Шаг {step / 100}")

            res = self.fetch_data(
                add_params={"priceU": f'{start_price};{finish_price}'}
            )
            data = self.get_price_range(data=res)

            if not data:
                logger.warning("Нет данных")
                start_price = finish_price

                step = self.max_step
                continue

            if data.total > self.max_count_of_good:
                logger.warning(f"{data.total} - дробим диапазон")

                sub_ranges = self.split_price_range(start_price, finish_price)
                result.extend(sub_ranges)

                start_price = finish_price
                step = self.default_step
                continue

            if data.total < self.low_goods_threshold:
                logger.info("Мало товаров")
                step = self.max_step

            else:
                step = self.default_step

            logger.info(f"Принят диапазон: {data.total}")

            result.append((
                DataPage(start_price, finish_price, data.total)
            ))
            start_price = finish_price

        logger.info(f"Всего получилось {len(result)} диапазонов")
        logger.info(result[1:5])
        return result


