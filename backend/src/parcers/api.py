from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import asyncio
import csv
import hmac
import os
import secrets
from io import StringIO
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import accounts, monitoring, oauth
from .service import MarketplaceSearchService, PROVIDER_FETCH_CAP
from .regions import REGIONS, get_region
from .pickup import pickup_service, yandex_keys

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
    accounts.init_db()
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
SESSION_SECRET = os.getenv("MULTIMARKET_SESSION_SECRET", "").strip() or secrets.token_urlsafe(48)
SESSION_HTTPS_ONLY = os.getenv("MULTIMARKET_COOKIE_SECURE", "false").strip().lower() in {
    "1", "true", "yes", "on",
}
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="multimarket_session",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)


@app.middleware("http")
async def private_response_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/auth", "/api/monitors", "/api/alerts", "/api/admin")):
        response.headers["Cache-Control"] = "no-store"
    return response


class BatchSearchRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=10)
    limit: int = Field(default=20, ge=1, le=50)


class MonitorCreate(BaseModel):
    query: str = Field(min_length=1, max_length=160)
    product_url: str = Field(min_length=10, max_length=2048)
    marketplace: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    interval_seconds: int = Field(default=3600, ge=900, le=604800)


class MonitorUpdate(BaseModel):
    active: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=900, le=604800)


class PasswordLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordRegister(PasswordLogin):
    name: str = Field(min_length=1, max_length=160)


class AdminRoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


def _admin_emails() -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv("MULTIMARKET_ADMIN_EMAILS", "").split(",")
        if item.strip()
    }


def _current_user(request: Request) -> dict | None:
    user = accounts.get_user(request.session.get("user_id"))
    if user is None and request.session.get("user_id"):
        request.session.pop("user_id", None)
        request.session.pop("csrf_token", None)
    return user


def _require_user(request: Request) -> dict:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт")
    return user


def _require_admin(request: Request) -> dict:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт")
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администратора")
    return user


def _check_csrf(request: Request) -> None:
    expected = request.session.get("csrf_token", "")
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Проверка запроса не пройдена")


def _safe_next_path(value: str | None) -> str:
    if not value or "\\" in value:
        return "/account"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return "/account"
    return parsed.path + (("?" + parsed.query) if parsed.query else "")


def _private_page(path: Path) -> FileResponse:
    response = FileResponse(path)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(STATIC_DIR / "icons" / "favicon.ico", media_type="image/x-icon")


@app.get("/product", include_in_schema=False)
async def product_page():
    return FileResponse(STATIC_DIR / "product.html")


@app.get("/delivery", include_in_schema=False)
async def delivery_page():
    return FileResponse(STATIC_DIR / "delivery.html")


@app.get("/login", include_in_schema=False)
async def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/account", include_in_schema=False)
async def account_page(request: Request):
    if not _current_user(request):
        return RedirectResponse("/login?next=/account", status_code=303)
    return _private_page(STATIC_DIR / "account.html")


@app.get("/admin", include_in_schema=False)
async def admin_page(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login?next=/admin", status_code=303)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администратора")
    return _private_page(STATIC_DIR / "admin.html")


@app.get("/monitoring", include_in_schema=False)
async def monitoring_page(request: Request):
    if not _current_user(request):
        return RedirectResponse("/login?next=/monitoring", status_code=303)
    return _private_page(STATIC_DIR / "monitoring.html")


@app.get("/history", include_in_schema=False)
async def history_page(request: Request):
    if not _current_user(request):
        return RedirectResponse("/login?next=/history", status_code=303)
    return _private_page(STATIC_DIR / "history.html")


@app.get("/sources", include_in_schema=False)
async def sources_page():
    return FileResponse(STATIC_DIR / "sources.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "MultiMarket", "version": app.version}


@app.get("/api/auth/config")
async def auth_config(request: Request):
    user = _current_user(request)
    return {
        "password_login": True,
        "providers": oauth.configured_providers(),
        "authenticated": user is not None,
        "user": user,
    }


@app.get("/api/auth/me")
async def auth_me(request: Request):
    user = _current_user(request)
    if not request.session.get("csrf_token"):
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return {"authenticated": user is not None, "user": user,
            "csrf_token": request.session["csrf_token"]}


@app.post("/api/auth/register", status_code=201)
def password_register(payload: PasswordRegister, request: Request):
    _check_csrf(request)
    if not accounts.allow_auth_attempt(payload.email, request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте через 15 минут.")
    try:
        user = accounts.register_user(email=payload.email, password=payload.password, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session.clear()
    request.session.update(user_id=user["id"], csrf_token=secrets.token_urlsafe(32))
    return {"user": user, "authenticated": True}


@app.post("/api/auth/login")
def password_login(payload: PasswordLogin, request: Request):
    _check_csrf(request)
    if not accounts.allow_auth_attempt(payload.email, request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте через 15 минут.")
    user = accounts.authenticate_user(email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    request.session.clear()
    request.session.update(user_id=user["id"], csrf_token=secrets.token_urlsafe(32))
    return {"user": user, "authenticated": True}


@app.get("/auth/{provider}", include_in_schema=False)
async def begin_oauth(provider: str, request: Request):
    if provider not in {"google", "yandex"}:
        raise HTTPException(status_code=404, detail="Неизвестный провайдер входа")
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    try:
        destination = oauth.authorization_url(provider, state, verifier)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Вход через этот сервис ещё не настроен") from exc
    request.session.clear()
    accounts.save_oauth_transaction(state=state, provider=provider, verifier=verifier)
    request.session["oauth_state"] = state
    request.session["oauth_provider"] = provider
    request.session["oauth_next"] = _safe_next_path(request.query_params.get("next"))
    return RedirectResponse(destination, status_code=302)


@app.get("/auth/{provider}/callback", include_in_schema=False)
async def finish_oauth(provider: str, request: Request):
    if provider not in {"google", "yandex"}:
        raise HTTPException(status_code=404, detail="Неизвестный провайдер входа")
    expected_state = request.session.pop("oauth_state", "")
    expected_provider = request.session.pop("oauth_provider", "")
    next_path = _safe_next_path(request.session.pop("oauth_next", "/account"))
    supplied_state = request.query_params.get("state", "")
    if (
        not expected_state
        or expected_provider != provider
        or not supplied_state
        or not hmac.compare_digest(expected_state, supplied_state)
    ):
        request.session.clear()
        raise HTTPException(status_code=400, detail="Сессия входа устарела. Начните вход заново.")
    verifier = accounts.consume_oauth_transaction(state=supplied_state, provider=provider)
    if not verifier:
        request.session.clear()
        raise HTTPException(status_code=400, detail="Сессия входа истекла. Начните вход заново.")
    if request.query_params.get("error") or not request.query_params.get("code"):
        request.session.clear()
        return RedirectResponse("/login?error=cancelled", status_code=303)
    try:
        profile = await oauth.fetch_profile(provider, request.query_params["code"], verifier)
        user = accounts.login_user(
            provider=provider,
            subject=str(profile["subject"]),
            email=profile.get("email") if isinstance(profile.get("email"), str) else None,
            name=profile.get("name") if isinstance(profile.get("name"), str) else None,
            picture_url=profile.get("picture_url") if isinstance(profile.get("picture_url"), str) else None,
            admin_emails=_admin_emails(),
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        request.session.clear()
        return RedirectResponse("/login?error=provider", status_code=303)
    request.session.clear()
    request.session["user_id"] = user["id"]
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return RedirectResponse(next_path, status_code=303)


@app.post("/auth/logout")
async def logout(request: Request):
    if request.session.get("user_id"):
        _check_csrf(request)
    request.session.clear()
    return {"logged_out": True}


@app.get("/api/admin/users")
async def admin_users(request: Request):
    _require_admin(request)
    return {"users": accounts.list_users()}


@app.patch("/api/admin/users/{user_id}")
async def update_user_role(user_id: str, payload: AdminRoleUpdate, request: Request):
    current_user = _require_admin(request)
    _check_csrf(request)
    target = accounts.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target["id"] == current_user["id"] and payload.role != "admin":
        raise HTTPException(status_code=409, detail="Нельзя снять права администратора со своего аккаунта")
    if target["role"] == "admin" and payload.role == "user" and accounts.admin_count() <= 1:
        raise HTTPException(status_code=409, detail="В системе должен остаться хотя бы один администратор")
    return accounts.set_role(user_id, payload.role)


@app.get("/api/regions")
async def regions():
    return {"regions": REGIONS}


@app.get("/api/pickup-points")
async def pickup_points(
    region_id: int = Query(ge=1, le=1000000),
    marketplace: str = Query(min_length=1, max_length=30),
    lat: float | None = Query(default=None, ge=-85, le=85),
    lon: float | None = Query(default=None, ge=-180, le=180),
    radius: float = Query(default=4, ge=.5, le=6),
):
    try:
        return await pickup_service.points(region_id, marketplace, lat, lon, radius)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "30"}) from exc


@app.get("/api/map-config")
async def map_config(response: Response):
    keys = yandex_keys()
    response.headers["Cache-Control"] = "no-store"
    # JS API keys are designed for the browser. Never return the server suggest key.
    return {"provider":"yandex", "api_key": keys["YANDEX_MAPS_API_KEY"],
            "yandex_suggest": bool(keys["YANDEX_MAPS_API_KEY"] and keys["YANDEX_SUGGEST_API_KEY"])}


@app.get("/api/address-suggestions")
async def address_suggestions(region_id: int = Query(ge=1, le=1000000), q: str = Query(min_length=3, max_length=160)):
    try:
        return await pickup_service.suggest(region_id, q)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "30"}) from exc


@app.get("/api/search")
async def search(
    q: str = Query(min_length=1, max_length=160, description="Название товара"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=PROVIDER_FETCH_CAP * 3),
    session_id: str | None = Query(default=None, min_length=8, max_length=80),
    region_id: int | None = Query(default=None, ge=1, le=1000000),
):
    try:
        if region_id is not None:
            get_region(region_id)
            return await search_service.search(q, limit, offset, session_id=session_id, region_id=region_id)
        if session_id:
            return await search_service.search(q, limit, offset, session_id=session_id)
        return await search_service.search(q, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/product-details")
async def product_details(
    marketplace: str = Query(min_length=1, max_length=80),
    product_url: str = Query(min_length=10, max_length=2048),
    region_id: int | None = Query(default=None, ge=1, le=1000000),
):
    try:
        get_region(region_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    allowed_domains = MARKETPLACE_DOMAINS.get(marketplace)
    parsed = urlparse(product_url)
    try:
        safe_port = parsed.port in (None, 443)
    except ValueError:
        safe_port = False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or not safe_port
        or not allowed_domains
        or not any(
            parsed.hostname == domain or parsed.hostname.endswith("." + domain)
            for domain in allowed_domains
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="Ссылка должна вести на HTTPS-карточку выбранного маркетплейса",
        )
    try:
        offer = await search_service.parse_product(marketplace, product_url, region_id=region_id) if region_id is not None else await search_service.parse_product(marketplace, product_url)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Карточка не ответила вовремя") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Некорректная ссылка на товар") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Не удалось получить подробности с публичной страницы товара",
        ) from exc
    if offer is None:
        return {
            "details_available": False,
            "marketplace": marketplace,
            "url": product_url,
            "message": "Публичная страница не содержит поддерживаемых подробностей товара.",
        }
    return {"details_available": True, **asdict(offer)}


@app.post("/api/search/batch")
async def batch_search(payload: BatchSearchRequest):
    queries = [query.strip() for query in payload.queries]
    if any(not query for query in queries):
        raise HTTPException(status_code=422, detail="Запросы не должны быть пустыми")
    semaphore = asyncio.Semaphore(3)

    async def run_one(query: str):
        async with semaphore:
            try:
                return await search_service.search(query, payload.limit)
            except Exception as exc:
                return {"query": query, "error": type(exc).__name__, "products": [], "providers": []}

    return {"results": await asyncio.gather(*(run_one(query) for query in queries))}


@app.post("/api/monitors", status_code=201)
async def create_monitor(payload: MonitorCreate, request: Request):
    user = _require_user(request)
    _check_csrf(request)
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
            user_id=user["id"],
        )
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="Этот товар уже отслеживается")
        raise


@app.get("/api/monitors")
async def get_monitors(request: Request):
    return {"monitors": monitoring.list_monitors(_require_user(request)["id"])}


@app.get("/api/monitors/export.csv")
async def export_monitors(request: Request):
    user = _require_user(request)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["title", "marketplace", "product_url", "current_price", "currency", "active", "last_status"])
    for monitor in monitoring.list_monitors(user["id"]):
        writer.writerow([
            monitor["title"], monitor["marketplace"], monitor["product_url"],
            monitor["current_price"], monitor["currency"], monitor["active"],
            monitor["last_status"],
        ])
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="multimarket-monitors.csv"'},
    )


@app.patch("/api/monitors/{monitor_id}")
async def patch_monitor(monitor_id: str, payload: MonitorUpdate, request: Request):
    user = _require_user(request)
    _check_csrf(request)
    monitor = monitoring.update_monitor(
        monitor_id, user_id=user["id"], active=payload.active,
        interval_seconds=payload.interval_seconds,
    )
    if not monitor:
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return monitor


@app.delete("/api/monitors/{monitor_id}")
async def remove_monitor(monitor_id: str, request: Request):
    user = _require_user(request)
    _check_csrf(request)
    if not monitoring.delete_monitor(monitor_id, user["id"]):
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return {"deleted": True, "id": monitor_id}


@app.get("/api/monitors/{monitor_id}/history")
async def get_monitor_history(monitor_id: str, request: Request, limit: int = Query(default=200, ge=1, le=500)):
    if not monitoring.get_monitor(monitor_id, _require_user(request)["id"]):
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return {"monitor_id": monitor_id, "points": monitoring.price_history(monitor_id, limit)}


@app.get("/api/alerts")
async def get_alerts(
    request: Request,
    monitor_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    user = _require_user(request)
    if monitor_id and not monitoring.get_monitor(monitor_id, user["id"]):
        raise HTTPException(status_code=404, detail="Монитор не найден")
    return {"alerts": monitoring.list_alerts(monitor_id, limit, user["id"])}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
