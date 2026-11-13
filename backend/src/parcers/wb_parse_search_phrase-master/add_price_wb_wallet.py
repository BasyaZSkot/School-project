from loguru import logger

if __package__:
    from .get_price_wb_wallet import get_wallet_discount_percent, get_discount_settings, calc_price_with_wb_wallet
else:
    from get_price_wb_wallet import get_wallet_discount_percent, get_discount_settings, calc_price_with_wb_wallet
if __package__:
    from .models import Item
else:
    from models import Item


def add_price_with_wb_wallet(item_models: list[Item]):
    discount_percent = get_wallet_discount_percent()
    max_price, _ = get_discount_settings()
    logger.info(f"Скидка для WB кошелька = {discount_percent}%")

    for product in item_models:
        product.wb_wallet = calc_price_with_wb_wallet(price=product.salePriceU,
                                                      discount_percent=discount_percent,
                                                      max_price=max_price
                                                      )

    return item_models
