import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from src.parcers import wb_media as media
from src.parcers.api import app


class MediaRoutingTests(unittest.TestCase):
    def setUp(self):
        self.expires = patch.object(media.routes, '_expires', time.monotonic() + 60)
        self.expires.start()
        self.addCleanup(self.expires.stop)

    def test_recent_product_uses_current_basket_not_old_41(self):
        self.assertEqual(media.image_url(1241343962), 'https://basket-44.wbbasket.ru/vol12413/part1241343/1241343962/images/big/1.webp')
        self.assertEqual(media.routes.calc_numb_basket(12677), '44')
        self.assertEqual(media.routes.calc_numb_basket(12678), '45')

    def test_invalid_routes_cannot_redirect_to_an_unrelated_host(self):
        for host in ['evil.test', 'basket-44.wbbasket.ru.evil.test', 'basket-44.wbbasket.ru/path']:
            with self.assertRaises(ValueError):media.routes.validate_routes([{'vol_range_from':0,'vol_range_to':100,'host':host}])

    def test_registry_outage_uses_bundled_routes_and_is_cached(self):
        with patch.object(media.routes, '_expires', 0), patch.object(media.routes, 'urlopen', side_effect=OSError) as request:
            self.assertIn('basket-44', media.image_url(1241343962))
            self.assertIn('basket-44', media.image_url(1241343962, 2))
            request.assert_called_once()

    def test_image_endpoint_corrects_saved_urls_and_validates_input(self):
        client=TestClient(app)
        self.addCleanup(client.close)
        response=client.get('/api/media/wb/1241343962/1',follow_redirects=False)
        self.assertEqual(response.status_code,307)
        self.assertEqual(response.headers['location'],media.image_url(1241343962))
        for path in ['/api/media/wb/0/1','/api/media/wb/1241343962/21','/api/media/wb/1241343962/0']:
            self.assertEqual(client.get(path,follow_redirects=False).status_code,404)

    def test_attributes_only_use_actual_options_and_never_invent_a_price(self):
        result=media.attributes({'nm_id':1241343962,'options':[{'name':'Процессор','value':'A15'}],'media':{'photo_count':3}},1241343962,'https://basket-44.wbbasket.ru/base')
        self.assertTrue(result['metadata_only'])
        self.assertEqual(result['specifications'],[{'name':'Процессор','value':'A15'}])
        self.assertEqual(len(result['image_urls']),3)
        self.assertNotIn('price',result)
        self.assertIsNone(media.attributes({'nm_id':99},1241343962,'https://example.test'))

    def test_details_endpoint_returns_metadata_without_replacing_saved_price(self):
        client=TestClient(app)
        self.addCleanup(client.close)
        with patch('src.parcers.api.search_service.parse_product',new_callable=AsyncMock,return_value=None),patch.object(media,'product_attributes',new_callable=AsyncMock,return_value={'details_available':True,'metadata_only':True,'specifications':[{'name':'Экран','value':'6.1'}]}):
            response=client.get('/api/product-details',params={'marketplace':'Wildberries','product_url':'https://www.wildberries.ru/catalog/1241343962/detail.aspx'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['metadata_only'])
        self.assertNotIn('price',response.json())
