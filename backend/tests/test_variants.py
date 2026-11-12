import unittest
from src.parcers.base import Offer,offer_group_key
from src.parcers.variants import extract

def offer(title,**kw):return Offer(marketplace="Ozon",title=title,price=100,currency="RUB",url="https://ozon.ru/product/1",**kw)

class VariantTests(unittest.TestCase):
    def test_storage_colors_and_ram_are_extracted(self):
        self.assertEqual(extract("Телефон 8/256 ГБ Black"),{"color":"чёрный","ram":"8 ГБ","storage":"256 ГБ"})
    def test_capacity_units_and_color_aliases_match(self):
        a=offer("Phone 1 TB Black",brand="X",model="Phone")
        b=offer("Phone 1024 ГБ чёрный",brand="X",model="Phone")
        self.assertEqual(offer_group_key(a),offer_group_key(b))
    def test_model_does_not_merge_different_memory(self):
        self.assertNotEqual(offer_group_key(offer("Phone 128 ГБ",brand="X",model="Phone")),offer_group_key(offer("Phone 256 ГБ",brand="X",model="Phone")))
    def test_gtin_does_not_hide_conflicting_variant_metadata(self):
        a=offer("Phone Black",gtin="12345678");b=offer("Phone White",gtin="12345678")
        self.assertNotEqual(offer_group_key(a),offer_group_key(b))
    def test_unknown_memory_is_not_assumed_equal_to_known_memory(self):
        self.assertNotEqual(offer_group_key(offer("Phone",brand="X",model="Phone")),offer_group_key(offer("Phone 128 GB",brand="X",model="Phone")))
    def test_condition_and_package_are_part_of_variant(self):
        a=offer("Phone",gtin="12345678",condition="новый");b=offer("Phone",gtin="12345678",condition="б/у")
        self.assertNotEqual(offer_group_key(a),offer_group_key(b))
        self.assertNotEqual(offer_group_key(a),offer_group_key(offer("Phone",gtin="12345678",condition="новый",variants={"package":"С зарядкой"})))
    def test_brand_word_is_not_a_guessed_colour(self):
        self.assertNotIn("color",extract("Black Shark 5",brand="Black Shark",model="5"))
    def test_specifications_override_title_guess(self):
        self.assertEqual(extract("Phone Blue",[{"name":"Цвет товара","value":"чёрный"}])["color"],"чёрный")
    def test_sellers_do_not_split_an_identical_variant(self):
        self.assertEqual(offer_group_key(offer("Phone 128 ГБ",seller="A")),offer_group_key(offer("Phone 128 ГБ",seller="B")))
    def test_frequencies_are_not_mistaken_for_storage(self):
        self.assertNotIn("storage",extract("Наушники 40000 Гц, Bluetooth 5.2"))


class VariantServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_preserves_variant_and_seller_metadata(self):
        from src.parcers.base import ProviderResult,SearchStatus
        from src.parcers.service import MarketplaceSearchService
        class Adapter:
            marketplace="Ozon"
            async def search(self,query,limit):return ProviderResult("Ozon",SearchStatus.READY,"https://ozon.ru",[offer("Phone 128 GB",brand="X",model="Phone",seller="Shop A"),offer("Phone 256 GB",brand="X",model="Phone",seller="Shop B")])
        result=await MarketplaceSearchService(adapters=[Adapter()]).search("Phone")
        self.assertEqual(len(result["products"]),2)
        self.assertEqual({p["offers"][0]["variants"]["storage"] for p in result["products"]},{"128 ГБ","256 ГБ"})
        self.assertEqual({p["offers"][0]["seller"] for p in result["products"]},{"Shop A","Shop B"})
