import json
import unittest

from src.parcers.yandex_about import extract_yandex_about
from src.parcers.ym import YandexMarketAdapter


def patch_widget(name, props):
    data = {"widgets": {name: {"/content/page/content/defaultPage/aboutProduct": props}}}
    return '<noframes data-apiary="patch">' + json.dumps(data) + '</noframes>'


class YandexAboutTests(unittest.TestCase):
    def test_full_characteristics_are_read_without_another_request(self):
        rows = [{"name":"Артикул Маркета","value":"123"},{"name":"Бренд","value":"Sony"},{"name":"Частота","value":"40000 Гц"}]
        html = patch_widget("@card/AboutFullSpecsListV2", {"specs":[{"name":"Характеристики","specs":{"compact":{"list":rows[:1]},"full":{"list":rows}}}]})
        self.assertEqual(extract_yandex_about(html)["specifications"],rows)

    def test_duplicate_copyable_spec_is_not_added_twice(self):
        row = {"name":"Артикул Маркета","value":"123"}
        html = patch_widget("@card/AboutSpecV2",row) + patch_widget("@card/AboutFullSpecsListV2",{"specs":[{"specs":{"full":{"list":[row]}}}]})
        self.assertEqual(extract_yandex_about(html)["specifications"],[row])

    def test_other_widgets_are_ignored_and_description_is_plain_text(self):
        html = patch_widget("@advertising/OtherProduct",{"specs":[{"specs":{"full":{"list":[{"name":"Бренд","value":"Other"}]}}}]})
        html += patch_widget("@card/AboutDescriptionV2",{"fullDescription":"<p>Описание <b>товара</b></p>"})
        result = extract_yandex_about(html)
        self.assertEqual(result["specifications"],[])
        self.assertEqual(result["description"],"Описание товара")

    def test_existing_product_parser_merges_about_widget_data(self):
        html = '<h1 data-auto="productCardTitle">Товар</h1><span data-auto="snippet-price-current">100 ₽</span>'
        html += patch_widget("@card/AboutFullSpecsListV2",{"specs":[{"specs":{"full":{"list":[{"name":"Бренд","value":"Sony"}]}}}]})
        adapter = YandexMarketAdapter(marketplace="Яндекс Маркет",search_url="https://market.yandex.ru/search?text={query}",allowed_hosts=("market.yandex.ru",))
        self.assertEqual(adapter._extract_product(html,"https://market.yandex.ru/card/item/123").specifications,[{"name":"Бренд","value":"Sony"}])


if __name__ == "__main__": unittest.main()
