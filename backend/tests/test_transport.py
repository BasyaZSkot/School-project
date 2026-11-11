import random
import sys
import types
import unittest

import httpx

from src.parcers.service import MarketplaceSearchService
from src.parcers.transport import (
    BlockedError,
    FetcherConfig,
    ProxyPool,
    ResilientFetcher,
    looks_like_challenge,
    make_client_factory,
    parse_proxy_urls,
)

URL = "https://www.ozon.ru/search/?text=tv"
BIG_PAGE = "<html>" + "x" * 30_000 + "</html>"


class Harness:
    """Scripted responses plus a record of how each request was made."""

    def __init__(self, responses, **config):
        self.responses = list(responses)
        self.calls = []
        self.sleeps = []
        self.now = 1000.0
        config.setdefault("min_interval", 0.0)
        config.setdefault("jitter", 0.0)
        self.fetcher = ResilientFetcher(
            FetcherConfig(**config),
            client_factory=self._factory,
            sleep=self._sleep,
            clock=lambda: self.now,
            rng=random.Random(1),
        )

    async def _sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def _factory(self, proxy, headers, cookies, timeout):
        def handler(request):
            self.calls.append({"proxy": proxy, "headers": dict(request.headers)})
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            status, kwargs = item if isinstance(item, tuple) else (item, {})
            return httpx.Response(status, request=request, **kwargs)

        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers=headers,
            cookies=cookies,
            follow_redirects=True,
        )


class ResilientFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_page_and_sends_browser_headers(self):
        h = Harness([(200, {"text": BIG_PAGE})])
        page = await h.fetcher.fetch(URL)
        self.assertEqual(page.status_code, 200)
        headers = h.calls[0]["headers"]
        self.assertIn("chrome/", headers["user-agent"].lower())
        self.assertEqual(headers["sec-fetch-dest"], "document")
        self.assertTrue(headers["accept-language"].startswith("ru"))

    async def test_retries_server_error_with_backoff(self):
        h = Harness([503, 502, (200, {"text": BIG_PAGE})])
        page = await h.fetcher.fetch(URL)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(h.calls), 3)
        self.assertEqual(len(h.sleeps), 2)
        self.assertGreater(h.sleeps[1], h.sleeps[0])

    async def test_honours_retry_after_on_429(self):
        h = Harness([(429, {"headers": {"Retry-After": "7"}}), (200, {"text": BIG_PAGE})])
        await h.fetcher.fetch(URL)
        self.assertEqual(h.sleeps, [7.0])

    async def test_retry_after_is_capped(self):
        h = Harness(
            [(429, {"headers": {"Retry-After": "9999"}}), (200, {"text": BIG_PAGE})],
            total_timeout=100.0,
        )
        await h.fetcher.fetch(URL)
        self.assertEqual(h.sleeps, [30.0])

    async def test_retry_after_longer_than_deadline_surfaces_the_block(self):
        h = Harness([(429, {"headers": {"Retry-After": "9999"}}), (200, {"text": BIG_PAGE})])
        with self.assertRaises(httpx.HTTPStatusError):
            await h.fetcher.fetch(URL)
        self.assertEqual(len(h.calls), 1)

    async def test_persistent_block_raises_status_error_after_all_attempts(self):
        h = Harness([403, 403, 403])
        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            await h.fetcher.fetch(URL)
        self.assertEqual(ctx.exception.response.status_code, 403)
        self.assertEqual(len(h.calls), 3)

    async def test_not_found_is_not_retried(self):
        h = Harness([404, (200, {"text": BIG_PAGE})])
        with self.assertRaises(httpx.HTTPStatusError):
            await h.fetcher.fetch(URL)
        self.assertEqual(len(h.calls), 1)

    async def test_challenge_page_with_200_is_treated_as_block(self):
        captcha = "<html><title>Подтвердите, что вы не робот</title></html>"
        h = Harness([(200, {"text": captcha})] * 3)
        with self.assertRaises(BlockedError):
            await h.fetcher.fetch(URL)
        self.assertEqual(len(h.calls), 3)

    async def test_large_page_mentioning_captcha_is_not_a_challenge(self):
        page = "<script>var captcha = 1;</script>" + "x" * 30_000
        self.assertFalse(looks_like_challenge(page))
        h = Harness([(200, {"text": page})])
        self.assertEqual((await h.fetcher.fetch(URL)).status_code, 200)

    async def test_network_error_is_retried_then_raised(self):
        err = httpx.ConnectError("boom")
        failing = Harness([err, err, err])
        with self.assertRaises(httpx.ConnectError):
            await failing.fetcher.fetch(URL)
        self.assertEqual(len(failing.calls), 3)
        recovering = Harness([err, (200, {"text": BIG_PAGE})])
        self.assertEqual((await recovering.fetcher.fetch(URL)).status_code, 200)

    async def test_rotates_proxy_after_block(self):
        proxies = ("http://p1.example:8080", "http://p2.example:8080")
        h = Harness([403, (200, {"text": BIG_PAGE})], proxies=proxies)
        await h.fetcher.fetch(URL)
        self.assertEqual([c["proxy"] for c in h.calls], list(proxies))

    async def test_without_proxies_requests_are_direct(self):
        h = Harness([(200, {"text": BIG_PAGE})])
        await h.fetcher.fetch(URL)
        self.assertIsNone(h.calls[0]["proxy"])

    async def test_cookies_set_by_site_are_reused_and_dropped_after_block(self):
        h = Harness(
            [
                (200, {"text": BIG_PAGE, "headers": {"Set-Cookie": "sid=abc; Path=/"}}),
                403,
                (200, {"text": BIG_PAGE}),
            ],
            cache_ttl=0.0,
        )
        await h.fetcher.fetch(URL)
        await h.fetcher.fetch(URL + "&p=2")
        self.assertIn("sid=abc", h.calls[1]["headers"].get("cookie", ""))
        self.assertNotIn("cookie", h.calls[2]["headers"])

    async def test_overall_deadline_stops_retries_and_keeps_real_error(self):
        h = Harness([503] * 5, max_attempts=5, backoff_base=10.0, total_timeout=15.0)
        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            await h.fetcher.fetch(URL)
        self.assertEqual(ctx.exception.response.status_code, 503)
        self.assertLess(len(h.calls), 5)

    async def test_timeout_without_other_proxy_fails_fast(self):
        h = Harness([httpx.ConnectTimeout("silent"), (200, {"text": BIG_PAGE})])
        with self.assertRaises(httpx.ConnectTimeout):
            await h.fetcher.fetch(URL)
        self.assertEqual(len(h.calls), 1)

    async def test_timeout_is_retried_through_another_proxy(self):
        proxies = ("http://p1.example:8080", "http://p2.example:8080")
        h = Harness([httpx.ConnectTimeout("silent"), (200, {"text": BIG_PAGE})], proxies=proxies)
        await h.fetcher.fetch(URL)
        self.assertEqual([c["proxy"] for c in h.calls], list(proxies))

    async def test_cache_avoids_repeat_requests(self):
        h = Harness([(200, {"text": BIG_PAGE})], cache_ttl=60.0)
        await h.fetcher.fetch(URL)
        await h.fetcher.fetch(URL)
        self.assertEqual(len(h.calls), 1)

    async def test_per_host_rate_limit_spaces_requests(self):
        h = Harness([(200, {"text": BIG_PAGE})] * 2, min_interval=2.0, cache_ttl=0.0)
        await h.fetcher.fetch(URL)
        await h.fetcher.fetch(URL + "&p=2")
        self.assertTrue(any(delay > 0 for delay in h.sleeps))


def _install_curl_stub(handler):
    """Fake curl_cffi exposing just the API surface the adapter relies on."""
    exceptions = types.SimpleNamespace()

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    exceptions.RequestException = RequestException
    exceptions.Timeout = Timeout

    class Cookies(dict):
        def get_dict(self):
            return dict(self)

    class Reply:
        def __init__(self, status, text, headers, url):
            self.status_code = status
            self.content = text.encode()
            self.headers = headers
            self.url = url

    class AsyncSession:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.cookies = Cookies(kwargs.get("cookies") or {})
            self.closed = False
            AsyncSession.instances.append(self)

        async def get(self, url, **kwargs):
            result = handler(self, url)
            if isinstance(result, Exception):
                raise result
            status, text, headers = result
            self.cookies["sid"] = "from-site"
            return Reply(status, text, headers, url)

        async def close(self):
            self.closed = True

    requests_module = types.ModuleType("curl_cffi.requests")
    requests_module.AsyncSession = AsyncSession
    requests_module.exceptions = exceptions
    root = types.ModuleType("curl_cffi")
    root.requests = requests_module
    sys.modules["curl_cffi"] = root
    sys.modules["curl_cffi.requests"] = requests_module
    return AsyncSession, exceptions


class CurlImpersonationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._saved = {k: sys.modules.get(k) for k in ("curl_cffi", "curl_cffi.requests")}

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    def _fetcher(self, **config):
        config.setdefault("min_interval", 0.0)
        config.setdefault("jitter", 0.0)
        config.setdefault("impersonate", "chrome")
        return ResilientFetcher(
            FetcherConfig(**config), sleep=self._no_sleep, rng=random.Random(1)
        )

    async def _no_sleep(self, seconds):
        pass

    async def test_uses_browser_tls_session_and_converts_response(self):
        headers = {"content-type": "text/html; charset=utf-8", "content-encoding": "gzip"}
        session_type, _ = _install_curl_stub(lambda s, url: (200, BIG_PAGE, headers))
        page = await self._fetcher().fetch(URL)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.text, BIG_PAGE)
        session = session_type.instances[0]
        self.assertEqual(session.kwargs["impersonate"], "chrome")
        # Our own User-Agent / client hints must not override the fingerprint.
        sent = session.kwargs["headers"]
        self.assertEqual(list(sent), ["Accept-Language"])
        self.assertTrue(session.closed)

    async def test_proxy_and_cookies_are_passed_through(self):
        session_type, _ = _install_curl_stub(
            lambda s, url: (200, BIG_PAGE, {"content-type": "text/html"})
        )
        fetcher = self._fetcher(proxies=("http://p1.example:8080",), cache_ttl=0.0)
        await fetcher.fetch(URL)
        await fetcher.fetch(URL + "&p=2")
        first, second = session_type.instances
        self.assertEqual(first.kwargs["proxies"]["https"], "http://p1.example:8080")
        self.assertEqual(second.kwargs["cookies"], {"sid": "from-site"})

    async def test_block_status_and_timeout_map_to_httpx_errors(self):
        _install_curl_stub(lambda s, url: (498, "blocked", {}))
        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            await self._fetcher(max_attempts=2).fetch(URL)
        self.assertEqual(ctx.exception.response.status_code, 498)

        session_type, exceptions = _install_curl_stub(lambda s, url: exceptions_holder[0].Timeout("slow"))
        exceptions_holder = [exceptions]
        with self.assertRaises(httpx.ConnectTimeout):
            await self._fetcher().fetch(URL)

    def test_missing_library_gives_actionable_error(self):
        sys.modules["curl_cffi"] = None  # makes "import curl_cffi" raise ImportError
        with self.assertRaises(ValueError) as ctx:
            make_client_factory("chrome")
        self.assertIn("requirements-impersonate", str(ctx.exception))


class ProxyPoolTests(unittest.TestCase):
    def test_round_robin_and_cooldown(self):
        now = [0.0]
        pool = ProxyPool(["http://a:1", "http://b:1"], cooldown=100, clock=lambda: now[0])
        self.assertEqual(pool.acquire(), "http://a:1")
        pool.report_failure("http://a:1")
        self.assertEqual(pool.acquire(), "http://b:1")
        self.assertEqual(pool.acquire(), "http://b:1")  # a is resting
        now[0] = 101.0
        self.assertIn(pool.acquire(), {"http://a:1", "http://b:1"})

    def test_all_resting_never_falls_back_to_direct(self):
        pool = ProxyPool(["http://a:1"], cooldown=100, clock=lambda: 0.0)
        pool.report_failure("http://a:1")
        self.assertEqual(pool.acquire(), "http://a:1")

    def test_empty_pool_means_direct(self):
        self.assertIsNone(ProxyPool().acquire())


class ConfigTests(unittest.TestCase):
    def test_parse_proxy_urls(self):
        parsed = parse_proxy_urls("http://u:p@h1:8080, https://h2:3128\nhttp://u:p@h1:8080")
        self.assertEqual(parsed, ("http://u:p@h1:8080", "https://h2:3128"))

    def test_invalid_proxy_url_is_rejected_without_echoing_secret(self):
        with self.assertRaises(ValueError) as ctx:
            parse_proxy_urls("ftp://user:secret@host:1")
        self.assertNotIn("secret", str(ctx.exception))


class ServiceMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_timeout_message_mentions_proxy_setting(self):
        class Silent:
            marketplace = "Wildberries"
            search_url = "https://www.wildberries.ru/catalog/0/search.aspx?search={query}"

            async def search(self, query, limit=20):
                raise httpx.ConnectTimeout("silent")

        result = await MarketplaceSearchService([Silent()]).search("tv")
        provider = result["providers"][0]
        self.assertEqual(provider["status"], "error")
        self.assertIn("timeout", provider["message"])
        self.assertIn("MULTIMARKET_PROXY_URLS", provider["message"])

    async def test_challenge_is_reported_as_policy_restricted(self):
        class Blocked:
            marketplace = "Ozon"
            search_url = "https://www.ozon.ru/search/?text={query}"

            async def search(self, query, limit=20):
                raise BlockedError("challenge", 200)

        result = await MarketplaceSearchService([Blocked()]).search("tv")
        self.assertEqual(result["providers"][0]["status"], "policy_restricted")


if __name__ == "__main__":
    unittest.main()
