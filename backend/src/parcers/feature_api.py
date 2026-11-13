"""Account library, account recovery and personal notification endpoints."""
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import accounts, account_security, library, mailer, notifications


class EmailRequest(BaseModel):
    email: str = Field(min_length=3,max_length=254)


class TokenRequest(BaseModel):
    token: str = Field(min_length=40,max_length=100)


class ResetRequest(TokenRequest):
    password: str = Field(min_length=8,max_length=128)


class ProductSnapshot(BaseModel):
    title: str = Field(min_length=1,max_length=300)
    offers: list[dict] = Field(min_length=1,max_length=600)


class DeliveryRequest(BaseModel):
    region_id: int | None = Field(default=None,ge=1,le=1000000)
    choices: dict = Field(default_factory=dict)


class NotificationUpdate(BaseModel):
    email_enabled: bool | None = None
    telegram_enabled: bool | None = None


def install(app,require_user,check_csrf,static_dir):
    router=APIRouter()

    @router.get("/favorites",include_in_schema=False)
    async def favorite_page(request:Request):
        try:require_user(request)
        except HTTPException:return RedirectResponse("/login?next=/favorites",status_code=303)
        return FileResponse(static_dir/"favorites.html",headers={"Cache-Control":"no-store"})

    @router.get("/compare",include_in_schema=False)
    async def compare_page():return FileResponse(static_dir/"compare.html")

    @router.get("/notifications",include_in_schema=False)
    async def notification_page(request:Request):
        try:require_user(request)
        except HTTPException:return RedirectResponse("/login?next=/notifications",status_code=303)
        return FileResponse(static_dir/"notifications.html",headers={"Cache-Control":"no-store"})

    @router.get("/forgot-password",include_in_schema=False)
    @router.get("/reset-password",include_in_schema=False)
    @router.get("/confirm-email",include_in_schema=False)
    async def action_page():return FileResponse(static_dir/"account-action.html",headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})

    @router.get("/api/favorites")
    async def favorites(request:Request):return {"favorites":library.favorites(require_user(request)["id"])}

    @router.put("/api/favorites")
    async def save_favorite(payload:ProductSnapshot,request:Request):
        user=require_user(request);check_csrf(request)
        try:return library.save_favorite(user["id"],payload.model_dump())
        except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc

    @router.delete("/api/favorites/{item_id}")
    async def delete_favorite(item_id:str,request:Request):
        user=require_user(request);check_csrf(request)
        if not library.remove_favorite(user["id"],item_id):raise HTTPException(status_code=404,detail="Товар не найден")
        return {"deleted":True}

    @router.get("/api/preferences/delivery")
    async def get_delivery(request:Request):return {"delivery":library.delivery(require_user(request)["id"])}

    @router.put("/api/preferences/delivery")
    async def save_delivery(payload:DeliveryRequest,request:Request):
        user=require_user(request);check_csrf(request)
        try:return {"delivery":library.save_delivery(user["id"],payload.model_dump())}
        except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc

    @router.post("/api/auth/password-reset/request")
    def request_reset(payload:EmailRequest,request:Request,background_tasks:BackgroundTasks):
        check_csrf(request)
        if not accounts.allow_auth_attempt("reset:"+payload.email,request.client.host if request.client else "unknown"):raise HTTPException(status_code=429,detail="Слишком много запросов. Попробуйте через 15 минут.")
        if not mailer.settings():raise HTTPException(status_code=503,detail="Отправка писем пока недоступна. Попробуйте позже.")
        user=account_security.local_user(payload.email)
        if user:
            try:background_tasks.add_task(mailer.background_action_email,user,"reset",account_security.issue(user["id"],"reset"))
            except (RuntimeError,ValueError):pass  # Identical response for existing and unknown accounts.
        return {"message":"Если для этой почты есть аккаунт с паролем, мы отправим письмо для восстановления. Проверьте также папку «Спам»."}

    @router.post("/api/auth/password-reset/confirm")
    def confirm_reset(payload:ResetRequest,request:Request):
        check_csrf(request)
        if not accounts.allow_auth_attempt("reset-confirm",request.client.host if request.client else "unknown"):raise HTTPException(status_code=429,detail="Слишком много попыток. Попробуйте позже.")
        try:account_security.consume(payload.token,"reset",payload.password)
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
        request.session.clear()
        return {"message":"Пароль изменён. Войдите с новым паролем."}

    @router.post("/api/auth/email/request")
    def request_email(request:Request):
        user=require_user(request);check_csrf(request)
        if user["email_verified"]:return {"message":"Почта уже подтверждена."}
        if not user["email"]:raise HTTPException(status_code=409,detail="В аккаунте нет адреса почты")
        if not mailer.settings():raise HTTPException(status_code=503,detail="Отправка писем пока недоступна. Попробуйте позже.")
        try:mailer.action_email(user,"verify",account_security.issue(user["id"],"verify"))
        except ValueError as exc:raise HTTPException(status_code=429,detail=str(exc)) from exc
        except RuntimeError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc
        return {"message":"Письмо подтверждения отправлено. Ссылка действует 24 часа."}

    @router.post("/api/auth/email/confirm")
    def confirm_email(payload:TokenRequest,request:Request):
        check_csrf(request)
        try:account_security.consume(payload.token,"verify")
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
        return {"message":"Почта подтверждена."}

    @router.get("/api/notification-settings")
    async def notification_settings(request:Request):return notifications.settings(require_user(request)["id"])

    @router.patch("/api/notification-settings")
    async def set_notifications(payload:NotificationUpdate,request:Request):
        user=require_user(request);check_csrf(request)
        try:return notifications.update_settings(user["id"],**payload.model_dump())
        except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc

    @router.post("/api/notification-settings/telegram")
    async def telegram_connect(request:Request):
        user=require_user(request);check_csrf(request)
        try:return await notifications.connect_link(user["id"])
        except RuntimeError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc

    @router.delete("/api/notification-settings/telegram")
    async def telegram_disconnect(request:Request):
        user=require_user(request);check_csrf(request);notifications.disconnect(user["id"])
        return notifications.settings(user["id"])

    @router.patch("/api/alerts/{alert_id}/read")
    def read_alert(alert_id:int,request:Request):
        user=require_user(request);check_csrf(request)
        with accounts._connect() as db:
            result=db.execute("UPDATE price_alerts SET read_at=? WHERE id=? AND monitor_id IN (SELECT id FROM monitors WHERE user_id=?)",(accounts._now(),alert_id,user["id"]))
            if not result.rowcount:raise HTTPException(status_code=404,detail="Уведомление не найдено")
        return {"read":True}

    app.include_router(router)
