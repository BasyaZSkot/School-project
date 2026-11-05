from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .service import MarketplaceSearchService

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

app = FastAPI(
    title="MultiMarket Search API",
    version="0.3.0",
    description=(
        "Единый поиск MultiMarket. Источники без разрешённого доступа возвращают "
        "ссылку на поиск и статус вместо выдуманных цен."
    ),
)
search_service = MarketplaceSearchService()


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(STATIC_DIR / "index.html")


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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
