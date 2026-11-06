# Third-party parser references

## MaxDev43/Marketplace-Parser

Source: https://github.com/MaxDev43/Marketplace-Parser

License: MIT. Copyright (c) 2026 Max.

The Ozon search-card field mapping in `embedded_state.py` is adapted from the repository's pure `parse_search_items` parsing logic in `parsers/ozon.py`. The adapter changes the integration boundary: it consumes JSON already embedded in the public HTML response and does not use the source project's browser-session bootstrap or private API transport.

MIT License notice:

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## prog-time/grex

Source: https://github.com/prog-time/grex

The project requester confirmed written permission to use this repository. Ozon widgetStates parsing and Yandex Market data-auto selectors (search tiles and product-page fields) are adapted from crawlers/ozon.py and crawlers/yandex_market.py. The integration reads ordinary public HTML only; browser cookie capture, private API interception, proxy rotation, and CAPTCHA retry mechanisms are not included.

## Duff89/wb_parse_search_phrase

Source: https://github.com/Duff89/wb_parse_search_phrase

The project requester confirmed written permission to use this repository. Its Item field names and nested size price representation are adapted in the WB record mapper. MultiMarket's `wb_record_to_offer` adapts Item.fill_price_from_sizes behavior for nested size prices, kopeck conversion, stock, and image fields. The standalone fetcher, internal endpoint, cookie handling, and proxy settings are not used by the live search adapter.
