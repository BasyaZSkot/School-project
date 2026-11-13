import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.parcers import wb_items


class ItemsBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        wb_items._cache.clear()

    async def test_cancelled_request_does_not_restart_the_running_parser(self):
        import time
        def parse(**kwargs):
            time.sleep(.05)
            return [1, 2]
        source = Mock(side_effect=parse)
        with patch.object(wb_items, 'import_module', return_value=SimpleNamespace(parse=source)):
            first = asyncio.create_task(wb_items.fetch_items('cancel'))
            await asyncio.sleep(.01)
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertEqual(await wb_items.fetch_items('cancel'), [1, 2])
        self.assertEqual(source.call_count, 1)

    async def test_simultaneous_search_and_following_page_reuse_parser(self):
        import time
        def parse(*, search_phrase):
            time.sleep(.03)
            return list(range(200))
        source = Mock(side_effect=parse)
        with patch.object(wb_items, 'import_module', return_value=SimpleNamespace(parse=source)):
            first, second = await asyncio.gather(wb_items.fetch_items('reuse', 20), wb_items.fetch_items('reuse', 40))
            again = await wb_items.fetch_items('reuse', 200)
        self.assertEqual(first, list(range(20)))
        self.assertEqual(second, list(range(40)))
        self.assertEqual(len(again), 200)
        self.assertEqual(source.call_count, 1)

    async def test_regions_are_separate_and_failures_are_not_cached(self):
        from src.parcers.regions import region_scope
        source = Mock(side_effect=[RuntimeError('temporary'), [1], [2]])
        with patch.object(wb_items, 'import_module', return_value=SimpleNamespace(parse=source)):
            with self.assertRaises(RuntimeError):
                await wb_items.fetch_items('retry')
            with region_scope(213):
                self.assertEqual(await wb_items.fetch_items('retry'), [1])
            with region_scope(2):
                self.assertEqual(await wb_items.fetch_items('retry'), [2])
        self.assertEqual(source.call_count, 3)

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
