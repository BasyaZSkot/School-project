if __package__:
    from .calc_basket import calc_numb_basket
else:
    from calc_basket import calc_numb_basket
if __package__:
    from .models import Item
else:
    from models import Item


MAX_IMAGES = 10

def add_images(item_models: list[Item]):
    for product in item_models:

        short_id = product.id // 100000
        part = product.id // 1000
        try:
            basket = calc_numb_basket(short_id=short_id)
        except ValueError:
            product.image_links = ""
            continue

        base_url = (
            f"https://basket-{basket}.wbbasket.ru/"
            f"vol{short_id}/part{part}/{product.id}/images/big/"
        )

        image_count = min(product.pics, MAX_IMAGES)

        product.image_links = ";".join(
            base_url + f"{i}.webp"
            for i in range(1, image_count + 1)
        )

    return item_models
