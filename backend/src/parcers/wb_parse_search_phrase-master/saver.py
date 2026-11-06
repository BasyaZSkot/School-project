import os
import pyexcel as pe
from loguru import logger
from datetime import datetime

from models import Item

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


class SaveWbData:
    def __init__(self, filename: str = "wb"):
        self.filename = filename

    @staticmethod
    def now_for_title():
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%Y-%m-%d_%H-%M-%S")
        return formatted_datetime

    def generate_filepath(self, filename):
        """Генерирует абсолютный путь к файлу в папке results"""
        timestamp = self.now_for_title()
        filename_with_timestamp = f"{filename}-{timestamp}.xlsx"
        full_path = os.path.join(RESULTS_DIR, filename_with_timestamp)
        return full_path, filename_with_timestamp

    def book_save_to_path(self, book_data):
        file_path, full_filename = self.generate_filepath(filename=self.filename)
        logger.debug(file_path)

        new_book = pe.Book(book_data)
        new_book.save_as(file_path)
        return full_filename

    def wb_save(self, products: list[Item]):
        data = [
            ["артикул",
             "ссылка",
             "название",
             "цена",
             "цена со скидкой",
             "цена с wb кошельком",
             "бренд",
             "рейтинг",
             "количество",
             "id продавца",
             "название продавца",
             "рейтинг продавца",
             "изображения",
             "кол-во оценок",
             "общее название предмета"
             ],
        ]

        all_saved_sku = []  # для контроля дублей
        for product in products:
            if not product:
                continue

            if str(product.id) in all_saved_sku:
                continue

            all_saved_sku.append(str(product.id))

            data.append(
                [product.id,
                 f"\u200Bhttps://www.wildberries.ru/catalog/{product.id}/detail.aspx",
                 product.name,
                 product.priceU,
                 product.salePriceU,
                 product.wb_wallet,
                 product.brand,
                 product.reviewRating,
                 product.totalQuantity,
                 product.supplierId,
                 product.supplier,
                 product.supplierRating,
                 product.image_links,
                 product.feedbacks,
                 product.entity
                 ]
            )
        book_data = {"Sheet_1": data,
                     }
        full_filename = self.book_save_to_path(book_data=book_data)
        logger.debug(full_filename)
        return full_filename



