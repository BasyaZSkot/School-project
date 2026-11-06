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

Reviewed as a technical reference for marketplace-specific field handling. GitHub does not declare a license for this repository, so no Grex source code is copied or redistributed. Browser cookie capture, private API interception, proxy rotation, and CAPTCHA retry mechanisms are intentionally not included.

## Duff89/wb_parse_search_phrase

Source: https://github.com/Duff89/wb_parse_search_phrase

The repository was reviewed for its Item field names and price representation. GitHub does not declare a license for this repository, so no source files are copied or redistributed. MultiMarket's `wb_record_to_offer` is an independently implemented mapper for compatible records; it converts kopecks to RUB, reads nested size prices and maps available stock/image fields. The standalone fetcher, internal endpoint, cookie handling, and proxy settings are not called by the live search adapter.
