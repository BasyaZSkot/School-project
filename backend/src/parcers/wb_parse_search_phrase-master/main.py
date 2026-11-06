import asyncio

from loguru import logger

from add_images import add_images
from add_price_wb_wallet import add_price_with_wb_wallet
from get_price_range import WbSearchPhraseParserRange
from get_token import get_token
from models import Items
from saver import SaveWbData
from wb_catalog_parser import WbCatalogAsyncFetcher


def parse(search_phrase):
    wb_token = get_token()

    cookies = {
        'x_wbaas_token': wb_token,
    }
    # Собираем ценовые промежутки
    price_ranges = WbSearchPhraseParserRange(search_phrase=search_phrase, cookies=cookies).parse()

    # Парсинг товаров
    fetcher = WbCatalogAsyncFetcher(search_phrase=search_phrase, pages=price_ranges, cookies=cookies)

    results = asyncio.run(fetcher.fetch_all())

    logger.info("Сырые json получены, перехожу к валидации")

    product_models = []
    for raw_data in results:
        try:
            items_info = Items.model_validate(raw_data)
            if items_info.products:
                product_models.extend(items_info.products)
        except Exception as err:
            logger.error(err)

    logger.info("Добавляем картинки")
    product_models = add_images(product_models)

    logger.info("Добавляем цену с WB-кошельком")
    product_models = add_price_with_wb_wallet(product_models)

    logger.info("Данные добавлены, перехожу к сохранению")
    SaveWbData().wb_save(products=product_models)


if __name__ == "__main__":
    parse(search_phrase="кроссовки мужские")