import unittest
from urllib.parse import quote
from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.service import MarketplaceSearchService


def offer(market, title, **kwargs):
    return Offer(marketplace=market, title=title, price=kwargs.pop('price', 100), currency='RUB',
                 url='https://example.test/'+market+'/'+quote(title,safe=''), **kwargs)


class Adapter:
    def __init__(self, items): self.items=items; self.marketplace=items[0].marketplace
    async def search(self, query, limit):
        return ProviderResult(self.marketplace, SearchStatus.READY, 'https://example.test', self.items)


class CrossMarketTests(unittest.IsolatedAsyncioTestCase):
    async def products(self, a, b):
        adapters=[Adapter([a,b])] if a.marketplace==b.marketplace else [Adapter([a]),Adapter([b])]
        return (await MarketplaceSearchService(adapters=adapters).search('test'))['products']

    async def test_iphone_titles_with_sim_and_app_details_group_together(self):
        a=offer('Яндекс Маркет','Смартфон Apple iPhone 16 128 ГБ Pink розовый, Dual eSIM, без RuStore и MAX',brand='Apple',seller='Созвон')
        b=offer('Яндекс Маркет','Смартфон Apple iPhone 16, 128ГБ Dual: NanoSim Pink (Розовый)',brand='Apple',seller='iGlobalShop')
        products=await self.products(a,b)
        self.assertEqual(len(products),1)
        self.assertEqual(len(products[0]['offers']),2)

    async def test_same_model_with_different_category_words_has_prices_together(self):
        a=offer('Wildberries', 'Кроссовки Air Force 1 форсы кеды', brand='Nike', price=3328)
        b=offer('Яндекс Маркет', 'Nike Air Force 1', brand='Nike', model='Air Force 1', price=4000)
        products=await self.products(a,b)
        self.assertEqual(len(products),1)
        self.assertEqual([o['price'] for o in products[0]['offers']],[3328,4000])

    async def test_punctuation_in_model_does_not_split_marketplaces(self):
        a=offer('Wildberries','Беспроводные наушники Sony WH1000XM5',brand='Sony')
        b=offer('Яндекс Маркет','Sony WH-1000XM5',brand='Sony',model='WH-1000XM5')
        self.assertEqual(len(await self.products(a,b)),1)

    async def test_different_models_colors_sizes_and_gtins_remain_separate(self):
        a=offer('Wildberries','Nike Air Force 1 white',brand='Nike')
        for b in [offer('Яндекс Маркет','Nike Air Force 2',brand='Nike'),
                  offer('Яндекс Маркет','Nike Air Force 1 black',brand='Nike'),
                  offer('Яндекс Маркет','Nike Air Force 1',brand='Nike',specifications=[{'name':'Размер','value':'42'}])]:
            self.assertEqual(len(await self.products(a,b)),2)
        a.gtin='4601234567890'
        b=offer('Яндекс Маркет','Nike Air Force 1',brand='Nike',gtin='4601234567891')
        self.assertEqual(len(await self.products(a,b)),2)

    async def test_generic_category_names_are_not_guessed_to_be_the_same_model(self):
        a=offer('Wildberries','Кроссовки зимние',brand='Nike')
        b=offer('Яндекс Маркет','Nike зимняя обувь',brand='Nike')
        self.assertEqual(len(await self.products(a,b)),2)

    async def test_same_model_from_different_sellers_on_same_marketplace_merges(self):
        a=offer('Wildberries','Смартфон Apple iPhone 14 128 ГБ Black',brand='Apple',seller='Shop A')
        b=offer('Wildberries','iPhone 14 128GB чёрный',seller='Shop B',price=90)
        products=await self.products(a,b)
        self.assertEqual(len(products),1)
        self.assertEqual({o['seller'] for o in products[0]['offers']},{'Shop A','Shop B'})

    async def test_conflicting_extra_specs_do_not_merge(self):
        for name,values in [('Процессор',('A15','A16')),('Диагональ экрана',('6.1','6.7')),('Емкость аккумулятора',('3000 мАч','4000 мАч')),('Количество SIM-карт',('1','2')),('Материал',('кожа','текстиль')),('Артикул производителя',('AB1','AB2'))]:
            a=offer('Wildberries','Phone X14',specifications=[{'name':name,'value':values[0]}])
            b=offer('Яндекс Маркет','Phone X14',specifications=[{'name':name,'value':values[1]}])
            with self.subTest(name=name):self.assertEqual(len(await self.products(a,b)),2)

    async def test_aliases_and_decimal_units_match(self):
        a=offer('Wildberries','Phone X14',specifications=[{'name':'Диагональ','value':'6,1'}])
        b=offer('Яндекс Маркет','Phone X14',specifications=[{'name':'Диагональ экрана','value':'6.1'}])
        self.assertEqual(len(await self.products(a,b)),1)

    async def test_pro_max_capacity_and_condition_stay_separate(self):
        a=offer('Wildberries','Apple iPhone 14 128 GB',brand='Apple')
        for title in ['iPhone 15 128 GB','iPhone 14 Pro 128 GB','iPhone 14 256 GB','iPhone 14 128 GB Витринный образец','iPhone 14 128 GB Восстановленный']:
            with self.subTest(title=title):self.assertEqual(len(await self.products(a,offer('Wildberries',title,brand='Apple'))),2)

    async def test_incomplete_offer_cannot_bridge_known_conflicting_colors(self):
        class Many:
            marketplace='Wildberries'
            async def search(self,query,limit):
                return ProviderResult(self.marketplace,SearchStatus.READY,'https://example.test',[offer(self.marketplace,'Phone X14'),offer(self.marketplace,'Phone X14 black'),offer(self.marketplace,'Phone X14 white')])
        products=(await MarketplaceSearchService(adapters=[Many()]).search('test'))['products']
        self.assertEqual(len(products),2)
        self.assertEqual(sorted(len(p['offers']) for p in products),[1,2])

    async def test_shared_product_id_does_not_discard_different_sellers(self):
        a=offer('Wildberries','Phone X14',external_id='123',seller='Shop A')
        b=offer('Wildberries','Phone X14',external_id='123',seller='Shop B',price=90)
        products=await self.products(a,b)
        self.assertEqual(len(products),1)
        self.assertEqual(len(products[0]['offers']),2)
