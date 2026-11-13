from pydantic import BaseModel, model_validator
from typing import Optional


class Price(BaseModel):
    basic: Optional[float] = None
    product: Optional[float] = None


class Size(BaseModel):
    price: Optional[Price] = None


class Item(BaseModel):
    id: int
    name: str
    salePriceU: Optional[float] = None
    priceU: Optional[float] = None
    wb_wallet: Optional[float] = None
    brand: str
    sale: Optional[int] = None
    rating: int
    volume: int
    supplier: str = None
    supplierId: int
    supplierRating: Optional[float] = None
    totalQuantity: int
    reviewRating: Optional[float]
    feedbacks: Optional[int]
    pics: int
    image_links: Optional[str] = None
    root: int
    feedback_count: Optional[int] = None
    valuation: Optional[str] = None
    description: Optional[str] = None
    characteristics: Optional[str] = None
    sizes: Optional[list[Size]] = None
    subj_root_name: Optional[str] = None
    subj_name: Optional[str] = None
    entity: Optional[str] = None

    @model_validator(mode="after")
    def fill_price_from_sizes(self):

        if self.sizes and len(self.sizes) > 0:
            size = self.sizes[0]

            if size.price:
                if self.priceU is None and size.price.basic is not None:
                    self.priceU = float(size.price.basic) / 100

                if self.salePriceU is None and size.price.product is not None:
                    self.salePriceU = float(size.price.product) / 100

        return self


class Items(BaseModel):
    products: list[Item]
