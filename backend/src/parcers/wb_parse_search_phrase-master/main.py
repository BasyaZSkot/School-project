import asyncio

from loguru import logger

if __package__:
    from .add_images import add_images
    from .get_token import get_token
    from .models import Items
    from .wb_catalog_parser import WbCatalogAsyncFetcher
else:
    from add_images import add_images
    from get_token import get_token
    from models import Items
    from wb_catalog_parser import WbCatalogAsyncFetcher


def parse(search_phrase, include_wallet=False):
    wb_token = get_token()

    cookies = {
        'x_wbaas_token': wb_token,
    }
    # Первые две страницы обычной выдачи, без разбиения по ценам.
    fetcher = WbCatalogAsyncFetcher(search_phrase=search_phrase, cookies=cookies)

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

    product_models = product_models[:200]

    logger.info("Добавляем картинки")
    product_models = add_images(product_models)

    if include_wallet:
        if __package__:
            from .add_price_wb_wallet import add_price_with_wb_wallet
        else:
            from add_price_wb_wallet import add_price_with_wb_wallet
        product_models = add_price_with_wb_wallet(product_models)

    logger.info("Данные добавлены")
    return product_models


if __name__ == "__main__":
    print(parse(search_phrase="кроссовки мужские nike", include_wallet=True))
