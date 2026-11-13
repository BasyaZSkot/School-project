import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.parcers import wb_items


class ItemsBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_imports_main_parse_and_runs_off_event_loop(self):
        loop_thread = threading.get_ident()
        def parse(*, search_phrase):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            self.assertEqual(search_phrase, 'nike')
            return list(range(250))
        with patch.object(wb_items, 'import_module', return_value=SimpleNamespace(parse=parse)) as load:
            result = await wb_items.fetch_items('nike')
        self.assertEqual(result, list(range(200)))
        load.assert_called_once_with('.wb_parse_search_phrase-master.main', package='src.parcers')

    async def test_respects_smaller_requested_limit(self):
        with patch.object(wb_items, 'import_module', return_value=SimpleNamespace(parse=Mock(return_value=[1, 2, 3]))):
            self.assertEqual(await wb_items.fetch_items('test', 2), [1, 2])
