from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import monitoring
from .service import MarketplaceSearchService

BACKEND_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BACKEND_DIR / "static"
load_dotenv(BACKEND_DIR / ".env")

search_service = MarketplaceSearchService()
MARKETPLACE_DOMAINS = {
    "Ozon": ("ozon.ru",),
    "Wildberries": ("wildberries.ru", "wildberries.by", "wildberries.kz"),
    "Яндекс Маркет": ("market.yandex.ru",),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitoring.init_db()
    stop_event = asyncio.Event()
    task = asyncio.create_task(monitoring.monitoring_loop(search_service, stop_event))
    app.state.monitor_stop_event = stop_event
    app.state.monitor_task = task
    yield
    stop_event.set()
    await task


app = FastAPI(
    title="MultiMarket Search API",
    version="0.5.0",
    description=(
        "Единый поиск и мониторинг цен. Разрешённые партнёрские JSON-фиды "
        "подключаются через переменные окружения."
    ),
    lifespan=lifespan,
)


class MonitorCreate(BaseModel):
    query: str = Field(min_length=1, max_length=160)
    product_url: str = Field(min_length=10, max_length=2048)
    marketplace: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    interval_seconds: int = Field(default=3600, ge=900, le=604800)


class MonitorUpdate(BaseModel):
    active: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=900, le=604800)


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "MultiMarket", "version": app.version}


@app.get("/api/search")
async def search(
    q: str = Query(min_length=1, max_length=160, description="Название товара"),
    limit: int = Query(default=20, ge=1, le=50),
):
    try:
        return await search_service.search(q, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/monitors", status_code=201)
async def create_monitor(payload: MonitorCreate):
    parsed = urlparse(payload.product_url)
    allowed_domains = MARKETPLACE_DOMAINS.get(payload.marketplace)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=422, detail="product_url должен быть HTTPS URL")
    if not allowed_domains or not any(
        parsed.hostname == domain or parsed.hostname.endswith("." + domain)
        for domain in allowed_domains
    ):
        raise HTTPException(
            status_code=422,
            detail="Домен товара не соответствует выбранному маркетплейсу",
        )
    try:
        return monitoring.create_monitor(
            query=payload.query.strip(),
            product_url=payload.product_url,
            marketplace=payload.marketplace.strip(),
            title=payload.title.strip(),
            interval_seconds=payload.interval_seconds,
        )
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Этот товар уже отслеживается")
        raise


@app.get("/api/monitors")
async def get_monitors():
    return {"monitors": monitoring.list_monitors()}


@app.patch("/api/monitors/{monitor_id}")
async def patch_monitor(monitor_id: str, payload: MonitorUpdate):
    monitor = monitoring.update_monitor(
        monitor_id, active=payload.active,
        interval_seconds=payload.interval_seconds,
    )
    if not monitor:
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return monitor


@app.delete("/api/monitors/{monitor_id}")
async def remove_monitor(monitor_id: str):
    if not monitoring.delete_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return {"deleted": True, "id": monitor_id}


@app.get("/api/monitors/{monitor_id}/history")
async def get_monitor_history(monitor_id: str, limit: int = Query(default=200, ge=1, le=500)):
    if not monitoring.get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return {"monitor_id": monitor_id, "points": monitoring.price_history(monitor_id, limit)}


@app.get("/api/alerts")
async def get_alerts(
    monitor_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    return {"alerts": monitoring.list_alerts(monitor_id, limit)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
