from fastapi import FastAPI, HTTPException, Query

from .service import MarketplaceSearchService

app = FastAPI(
    title="MultiMarket Search API",
    version="0.2.0",
    description=(
        "Единый поиск MultiMarket. Источники без разрешённого доступа возвращают "
        "ссылку на поиск и статус вместо выдуманных цен."
    ),
)
search_service = MarketplaceSearchService()


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "MultiMarket"}


@app.get("/api/search")
async def search(
    q: str = Query(min_length=1, max_length=160, description="Название товара"),
    limit: int = Query(default=20, ge=1, le=50),
):
    try:
        return await search_service.search(q, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
