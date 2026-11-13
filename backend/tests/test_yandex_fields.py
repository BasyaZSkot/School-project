import json
from html import escape
from pathlib import Path
import unittest
from src.parcers.ym import YandexMarketAdapter


def adapter():
    return YandexMarketAdapter(marketplace='Яндекс Маркет',search_url='https://market.yandex.ru/search?text={query}',allowed_hosts=('market.yandex.ru',))


def zone(name, data, content=''):
    return '<div data-zone-name="'+name+'" data-zone-data="'+escape(json.dumps(data),quote=True)+'">'+content+'</div>'


def card(sku, data):
    return '<article data-auto="searchOrganic">'+zone('productSnippet',data)+f'<a data-auto="galleryLink" href="/card/item/{sku}"><img src="https://cdn.example/{sku}/1.jpg"><img src="https://cdn.example/{sku}/2.jpg"></a><span data-auto="snippet-title">Sony WH-1000XM5</span><span data-auto="snippet-price-current">90 ₽</span></article>'


class YandexFieldsTests(unittest.TestCase):
    def test_snippet_metadata_supplies_same_card_fields_as_wb(self):
        brands=zone('filter',{'filterName':'Бренд'},zone('filterValue',{'valueId':'152955','value':'Sony'}))
        metadata={'marketSku':'123','vendorId':'152955','price':100,'additionalPrices':[{'priceType':'yaBank','priceValue':90}],
          'signals':[{'type':'shop','title':'Example seller'}], 'rating':{'rating':'4.8','gradesCount':'581','purchaseCount':'999','ratingType':'product'},'lastStock':{'stockItemCount':35}}
        offer=adapter()._extract(brands+card(123,metadata),'https://market.yandex.ru/search?text=sony',10)[0]
        self.assertEqual(offer.brand,'Sony');self.assertEqual(offer.seller,'Example seller')
        self.assertEqual(offer.rating,4.8);self.assertEqual(offer.review_count,581)
        self.assertTrue(offer.in_stock);self.assertEqual(offer.price,100)
        self.assertEqual(len(offer.image_urls),2)

    def test_cards_do_not_share_metadata_and_stock_zero_is_preserved(self):
        a={'marketSku':'1','vendorName':'Sony','lastStock':{'stockItemCount':0}}
        b={'marketSku':'2','vendorName':'Nike','signals':[{'type':'shop','title':'Second shop'}]}
        offers=adapter()._extract(card(1,a)+card(2,b),'https://market.yandex.ru/search',10)
        self.assertFalse(offers[0].in_stock);self.assertIsNone(offers[0].seller)
        self.assertEqual(offers[1].brand,'Nike');self.assertIsNone(offers[1].in_stock)

    def test_metadata_outside_card_and_non_brand_filter_cannot_enrich_product(self):
        other_filter=zone('filter',{'filterName':'Цвет'},zone('filterValue',{'valueId':'1','value':'Not a brand'}))
        wrong={'marketSku':'999','vendorName':'Wrong','price':1,'rating':{'rating':5,'gradesCount':2}}
        offer=adapter()._extract(other_filter+zone('productSnippet',wrong)+card(1,{}),'https://market.yandex.ru/search',10)[0]
        self.assertIsNone(offer.brand);self.assertIsNone(offer.rating);self.assertEqual(offer.price,90)

    def test_market_sku_can_differ_from_public_card_id(self):
        offer=adapter()._extract(card(1,{'marketSku':'999','vendorName':'Sony'}),'https://market.yandex.ru/search',10)[0]
        self.assertEqual(offer.brand,'Sony')

    def test_schema_fields_are_preserved_when_dom_snippet_exists(self):
        data={'@type':'Product','name':'Sony WH-1000XM5','url':'https://market.yandex.ru/card/item/123','description':'Description',
              'brand':{'name':'Sony'},'model':'WH-1000XM5','offers':{'price':90,'priceCurrency':'RUB','availability':'https://schema.org/OutOfStock','seller':{'name':'Schema shop'}}}
        html=card(123,{})+'<script type="application/ld+json">'+json.dumps(data)+'</script>'
        offer=adapter()._extract(html,'https://market.yandex.ru/search',10)[0]
        self.assertEqual(offer.description,'Description');self.assertEqual(offer.seller,'Schema shop');self.assertFalse(offer.in_stock)

    def test_about_specs_supply_brand_and_model_without_extra_fetches(self):
        props={'widgets':{'@card/AboutFullSpecsListV2':{'/content/page/content/defaultPage/aboutProduct':{'specs':[{'specs':{'full':{'list':[{'name':'Бренд','value':'Sony'},{'name':'Линейка','value':'WH-1000XM5'}]}}}]}}}}
        html='<h1 data-auto="productCardTitle">Sony headphones</h1><span data-auto="snippet-price-current">100 ₽</span><noframes data-apiary="patch">'+json.dumps(props)+'</noframes>'
        offer=adapter()._extract_product(html,'https://market.yandex.ru/card/item/123')
        self.assertEqual(offer.brand,'Sony');self.assertEqual(offer.model,'WH-1000XM5')
