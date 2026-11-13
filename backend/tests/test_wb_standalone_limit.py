import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

FOLDER = Path(__file__).resolve().parents[1] / 'src/parcers/wb_parse_search_phrase-master'


def load_fetcher():
    spec = importlib.util.spec_from_file_location('standalone_wb_catalog', FOLDER / 'wb_catalog_parser.py')
    module = importlib.util.module_from_spec(spec)
    # Logging and the unused legacy range DTO are not required to test pagination.
    with patch.dict(sys.modules, {'loguru': SimpleNamespace(logger=Mock()),
                                 'common_data': SimpleNamespace(HEADERS={}),
                                 'dto': SimpleNamespace(DataPage=object)}):
        spec.loader.exec_module(module)
    return module.WbCatalogAsyncFetcher


class StandaloneWbLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_first_two_pages_without_price_partitioning(self):
        fetcher = load_fetcher()(search_phrase='test', cookies={})
        self.assertEqual(fetcher._build_task(), [{'page': 1}, {'page': 2}])
        self.assertNotIn('priceU', fetcher._build_params({'page': 1}))
        async def response(client, task):
            start = (task['page'] - 1) * 150
            return {'products': [{'id': i} for i in range(start, start + 150)]}
        fetcher._fetch_one = AsyncMock(side_effect=response)
        result = await fetcher.fetch_all()
        ids = [p['id'] for page in result for p in page['products']]
        self.assertEqual(ids, list(range(200)))
        self.assertEqual(fetcher._fetch_one.await_count, 2)

    async def test_duplicates_and_short_results_preserve_source_order(self):
        fetcher = load_fetcher()(search_phrase='test', cookies={})
        fetcher._fetch_one = AsyncMock(side_effect=[{'products': [{'id': 3}, {'id': 1}]},
            {'data': {'products': [{'id': 1}, {'id': 2}]}}])
        result = await fetcher.fetch_all()
        self.assertEqual([p['id'] for page in result for p in page['products']], [3, 1, 2])

    def test_main_does_not_scan_price_ranges(self):
        source = (FOLDER / 'main.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertNotIn('WbSearchPhraseParserRange', source)
        self.assertLess(source.index('product_models[:200]'), source.index('product_models = add_images'))
