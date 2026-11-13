import unittest
import httpx
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from src.parcers import wb_requests, ozon_requests, ym_requests
from src.parcers.wb import WildberriesAdapter
from src.parcers.ozon import OzonAdapter
from src.parcers.ym import YandexMarketAdapter
from src.parcers.regions import region_scope


class RequestsTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_get_and_each_retry_use_the_marketplace_sender(self):
        for module in (wb_requests, ozon_requests, ym_requests):
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(503 if len(calls) == 1 else 200, text='<html>Product page</html>')
            with patch.dict(module._fetchers, {}, clear=True), patch.object(module, 'send_get', AsyncMock(wraps=module.send_get)) as sender:
                fetcher = module.get_fetcher()
                fetcher._client_factory = lambda *args: httpx.AsyncClient(transport=httpx.MockTransport(respond))
                fetcher._sleep = AsyncMock()
                result = await module.fetch_public_page('https://example.test/product', lambda final, original: True)
                self.assertEqual(result, ('https://example.test/product', '<html>Product page</html>'))
                self.assertEqual(sender.await_count, 2)
                self.assertEqual([request.method for request in calls], ['GET', 'GET'])

    def test_marketplaces_and_regions_have_independent_clients(self):
        with patch.dict(wb_requests._fetchers, {}, clear=True), patch.dict(ozon_requests._fetchers, {}, clear=True), patch.dict(ym_requests._fetchers, {}, clear=True):
            a, b, c = [m.get_fetcher() for m in (wb_requests, ozon_requests, ym_requests)]
            self.assertEqual(len({id(a), id(b), id(c)}), 3)
            self.assertIs(a, wb_requests.get_fetcher())
            with region_scope(213):
                regional = wb_requests.get_fetcher()
                self.assertIsNot(a, regional)
                self.assertIs(regional, wb_requests.get_fetcher())
            self.assertIs(a, wb_requests.get_fetcher())

    async def test_adapters_dispatch_to_their_own_request_module(self):
        for cls, module in [(WildberriesAdapter, wb_requests), (OzonAdapter, ozon_requests), (YandexMarketAdapter, ym_requests)]:
            adapter = cls.from_env()
            with patch.object(module, 'fetch_public_page', AsyncMock(return_value=('url', 'html'))) as fetch:
                self.assertEqual(await adapter._fetch_public_page('url'), ('url', 'html'))
                fetch.assert_awaited_once_with('url', adapter._valid_marketplace_url, adapter._fetcher)

    async def test_redirect_checks_and_injected_fetchers_are_preserved(self):
        for module in (wb_requests, ozon_requests, ym_requests):
            fetcher = SimpleNamespace(fetch=AsyncMock(return_value=SimpleNamespace(url='https://evil.test', text='html')))
            with self.assertRaises(ValueError):
                await module.fetch_public_page('https://market.yandex.ru/card/a/1', lambda final, original: False, fetcher)
            with region_scope(213):
                await module.fetch_public_page('https://market.yandex.ru/card/a/1', lambda final, original: True, fetcher)
            self.assertIn('lr=213', fetcher.fetch.call_args.args[0])
