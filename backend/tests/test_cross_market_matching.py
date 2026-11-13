import unittest
from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.service import MarketplaceSearchService


def offer(market, title, **kwargs):
    return Offer(marketplace=market, title=title, price=kwargs.pop('price', 100), currency='RUB',
                 url='https://example.test/'+market, **kwargs)


class Adapter:
    def __init__(self, item): self.item=item; self.marketplace=item.marketplace
    async def search(self, query, limit):
        return ProviderResult(self.marketplace, SearchStatus.READY, 'https://example.test', [self.item])


class CrossMarketTests(unittest.IsolatedAsyncioTestCase):
    async def products(self, a, b):
        return (await MarketplaceSearchService(adapters=[Adapter(a), Adapter(b)]).search('test'))['products']

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
        a=offer('Wildberries','Nike Air Force 1',brand='Nike')
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
