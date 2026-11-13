import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from src.parcers.api import app
from src.parcers.base import Offer, ProviderResult, SearchStatus
from src.parcers.service import MarketplaceSearchService


class Source:
    def __init__(self, market, start, brand='Test'):
        self.marketplace=market;self.calls=[]
        self.offers=[Offer(marketplace=market,title=f'{brand} X{i}',brand=brand,model=f'X{i}',price=100+i,
            currency='RUB',url=f'https://example.test/{market}/{i}',external_id=str(i)) for i in range(start,start+250)]
    async def search(self, query, limit):
        self.calls.append(limit)
        # Intentionally over-return: service must enforce its own per-source cap.
        return ProviderResult(self.marketplace,SearchStatus.READY,'https://example.test',self.offers)


class CollectTests(unittest.IsolatedAsyncioTestCase):
    async def test_200_per_marketplace_keep_unmatched_and_merge_common_models(self):
        wb,ym=Source('Wildberries',0),Source('Яндекс Маркет',100)
        data=await MarketplaceSearchService(adapters=[wb,ym]).search('test',limit=200,collect_all=True)
        self.assertEqual(wb.calls,[200]);self.assertEqual(ym.calls,[200])
        self.assertEqual(data['total_offers'],400)
        self.assertEqual(len(data['products']),300)
        self.assertEqual(sum(len(p['offers'])==2 for p in data['products']),100)
        self.assertEqual(sum(len(p['offers'])==1 for p in data['products']),200)
        self.assertFalse(data['has_more'])

    async def test_no_matches_returns_all_400_cards_in_one_response(self):
        sources=[Source('Wildberries',0,'BrandA'),Source('Яндекс Маркет',0,'BrandB')]
        data=await MarketplaceSearchService(adapters=sources).search('test',collect_all=True)
        self.assertEqual(len(data['products']),400)
        self.assertEqual(data['result_scope'],'first_200_per_marketplace')

    async def test_three_enabled_sources_are_each_capped_at_200(self):
        sources=[Source('Wildberries',0,'BrandA'),Source('Яндекс Маркет',0,'BrandB'),Source('Ozon',0,'BrandC')]
        data=await MarketplaceSearchService(adapters=sources).search('test',collect_all=True)
        self.assertEqual(len(data['products']),600)
        self.assertTrue(all(s.calls==[200] for s in sources))

    async def test_collect_all_rejects_nonzero_offset(self):
        with self.assertRaises(ValueError):
            await MarketplaceSearchService(adapters=[Source('Wildberries',0)]).search('test',offset=20,collect_all=True)

    def test_http_flag_is_forwarded_without_changing_old_pagination(self):
        with TestClient(app) as client, patch('src.parcers.api.search_service.search',AsyncMock(return_value={'products':[]})) as search:
            self.assertEqual(client.get('/api/search',params={'q':'nike','collect_all':'true','region_id':213}).status_code,200)
            search.assert_awaited_once_with('nike',20,0,session_id=None,region_id=213,collect_all=True)
