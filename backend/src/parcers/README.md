# MultiMarket marketplace connectors

## What is implemented

- One asynchronous search service for Ozon, Wildberries and Yandex Market.
- Shared `Offer` model with validated price, currency and HTTPS product URL.
- Concurrent provider requests with per-provider timeouts and isolated errors.
- Conservative product grouping by valid GTIN, brand + model, or exact normalized title.
- Currency-aware price grouping: RUB and USD are never compared as if they were the same unit.
- Wildberries source-compatible record mapping in `wb_adapter.py`, including nested size prices and kopecks-to-rubles conversion.
- Optional normalized JSON partner-feed adapters configured by environment variables.
- FastAPI endpoints and responsive Russian-language search UI.
- Unit/API tests and a GitHub Actions workflow.

## Live data status

When no partner feed is configured, each default adapter makes one best-effort HTTPS request to that marketplace's public search page and reads only product data already embedded in the returned HTML. Price monitors revisit the selected public product page and use embedded state, Schema.org data, or the marketplace's public HTML fields when available. The service does not log in, reuse browser cookies, call undocumented private APIs, solve CAPTCHA, or evade access controls. Public pages can omit product data or restrict automated requests, so live results are not guaranteed. A configured licensed/partner JSON feed takes precedence for its marketplace.

A live feed must return this shape:

```json
{
  "offers": [
    {
      "id": "sku-123",
      "title": "Product name",
      "price": 1299.5,
      "currency": "RUB",
      "url": "https://marketplace.example/product/sku-123",
      "brand": "Brand",
      "model": "Model",
      "gtin": "4601234567890",
      "in_stock": true,
      "image_url": "https://cdn.example/image.webp"
    }
  ]
}
```

The endpoint receives `q` and `limit` query parameters. It must be an HTTPS endpoint that you are authorized to use. Optional bearer tokens are read from environment variables. The app never fabricates prices when a feed is absent or unavailable.

## Configure feeds

Copy `backend/.env.example` to `backend/.env` and fill only the endpoints and tokens supplied by an authorized partner:

- `MULTIMARKET_OZON_FEED_URL` / `MULTIMARKET_OZON_FEED_TOKEN`
- `MULTIMARKET_WB_FEED_URL` / `MULTIMARKET_WB_FEED_TOKEN`
- `MULTIMARKET_YM_FEED_URL` / `MULTIMARKET_YM_FEED_TOKEN`

Never commit `backend/.env`. It is excluded by `backend/.gitignore`. Do not paste credentials into chat or source code.

## Run locally

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
uvicorn src.parcers.api:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000`, `/api/health`, `/api/search?q=Sony%20headphones`, or `/docs`.

## Tests

From the repository root:

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

GitHub Actions runs the same test command on pushes to `main` and `feat/**`, and on pull requests targeting `main`.

## WB example parser integration

The example parser's data model and field names informed the WB mapper. The browser/session and internal-endpoint transport are not invoked by the MultiMarket service. If a permitted source becomes available, inject an async source callable into `WildberriesAdapter.from_record_source(source)` that returns records compatible with the example `Item` model.

Keep source rate limits, caching, attribution, currency and stock freshness explicit. Do not implement CAPTCHA solving, proxy rotation, browser fingerprint spoofing, or other access-control circumvention.
