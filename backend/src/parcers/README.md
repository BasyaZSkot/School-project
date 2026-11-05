# MultiMarket marketplace connectors

## Current state

This package provides a concurrent search service, a normalized offer contract,
conservative product grouping, provider status reporting, and direct buyer-search
links for Ozon, Wildberries, and Yandex Market.

**Live marketplace scraping is not enabled by default.** The WB example commit
contains a parser built around undocumented internal browser endpoints, browser
cookie acquisition, and a configured proxy. Those transport/access-control
pieces are intentionally not connected to the aggregator. The reusable record
mapping is implemented in `wb_adapter.py`: it converts records shaped like the
example parser's `Item` model into MultiMarket `Offer` objects. The WB
`*PriceU` fields are converted from kopecks to RUB.

The WB adapter accepts an injected async source callable. It remains in
`access_required` mode until an approved API, licensed feed, or written
permission is configured. No prices or stock are fabricated.

## Run locally

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
uvicorn src.parcers.api:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000/api/health`, `/api/search?q=Sony%20headphones`,
or `/docs`.

## WB mapping tests

From the repository root:

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

## Enabling live offers

Enable a provider only after an approved source is available: official API access,
a licensed affiliate/content feed, or written permission for a documented public
interface. Implement an async source returning records with the fields used by
`wb_record_to_offer`, or map the source's records directly to `Offer`.

Keep rate limits, caching, timeouts, source attribution, currency, and stock
freshness explicit. Do not add CAPTCHA solving, proxy rotation, browser
fingerprint spoofing, or other access-control circumvention.
