# MultiMarket marketplace connectors

## Current state

This package provides a concurrent search service, a normalized offer contract,
conservative product grouping, provider status reporting, and direct buyer-search
links for Ozon, Wildberries, and Yandex Market.

**It does not claim to scrape live prices.** There are no marketplace API credentials
or approved partner feeds configured, and the browser endpoints described in
`Parcer.md` are internal/undocumented interfaces.

The adapters return honest `access_required` or `policy_restricted` statuses and
search links. They never fabricate prices, stock, or offers.

## Run locally

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
uvicorn src.parcers.api:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000/api/health`, `/api/search?q=Sony%20headphones`,
or `/docs`.

## Enabling live offers

Enable a provider only after an approved source is available: official API access,
a licensed affiliate/content feed, or written permission for a documented public
interface. Implement `search(query, limit)` and map source records to `Offer`.
Keep rate limits, caching, timeouts, source attribution, currency, and stock
freshness explicit.

Do not add CAPTCHA solving, proxy rotation, browser fingerprint spoofing, or
other access-control circumvention.
