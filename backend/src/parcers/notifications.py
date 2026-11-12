"""Personal opt-in notification routing, delivery retries and Telegram binding."""
import asyncio
import hashlib
import os
import re
import secrets
import time
import sqlite3
import logging

import httpx
from . import accounts, mailer


def schema(db):
    for sql in (
        "CREATE TABLE IF NOT EXISTS notification_settings (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,email_enabled INTEGER NOT NULL DEFAULT 0,telegram_enabled INTEGER NOT NULL DEFAULT 0,chat_id INTEGER UNIQUE,telegram_name TEXT)",
        "CREATE TABLE IF NOT EXISTS telegram_links (token_hash TEXT PRIMARY KEY,user_id TEXT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires_at REAL NOT NULL)",
        "CREATE TABLE IF NOT EXISTS notification_deliveries (alert_id INTEGER NOT NULL,channel TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL DEFAULT 0,locked_until REAL NOT NULL DEFAULT 0,PRIMARY KEY(alert_id,channel))",
        "CREATE TABLE IF NOT EXISTS app_jobs (name TEXT PRIMARY KEY,value TEXT,expires_at REAL NOT NULL DEFAULT 0)",
    ): db.execute(sql)


def settings(user_id):
    with accounts._connect() as db:
        schema(db);db.execute("INSERT OR IGNORE INTO notification_settings(user_id) VALUES (?)",(user_id,))
        row=dict(db.execute("SELECT * FROM notification_settings WHERE user_id=?",(user_id,)).fetchone())
    user=accounts.get_user(user_id)
    return {"email_enabled":bool(row["email_enabled"]),"telegram_enabled":bool(row["telegram_enabled"]),
            "telegram_connected":row["chat_id"] is not None,"telegram_name":row["telegram_name"],
            "email_available":bool(mailer.settings() and user and user["email_verified"] and user["email"]),
            "telegram_available":bool(os.getenv("MULTIMARKET_TELEGRAM_BOT_TOKEN"))}


def update_settings(user_id,email_enabled=None,telegram_enabled=None):
    current=settings(user_id)
    if email_enabled and not current["email_available"]:raise ValueError("Для писем подтвердите почту. Отправка писем должна быть доступна.")
    if telegram_enabled and not(current["telegram_available"] and current["telegram_connected"]):raise ValueError("Сначала подключите Telegram")
    with accounts._connect() as db:
        if email_enabled is not None:db.execute("UPDATE notification_settings SET email_enabled=? WHERE user_id=?",(int(email_enabled),user_id))
        if telegram_enabled is not None:db.execute("UPDATE notification_settings SET telegram_enabled=? WHERE user_id=?",(int(telegram_enabled),user_id))
    return settings(user_id)


async def bot_call(method,**payload):
    token=os.getenv("MULTIMARKET_TELEGRAM_BOT_TOKEN","").strip()
    if not token:raise RuntimeError("Telegram пока не подключён")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.post(f"https://api.telegram.org/bot{token}/{method}",json=payload)
            response.raise_for_status();data=response.json()
        if not isinstance(data,dict) or not data.get("ok"):raise ValueError("Bot response rejected")
        return data.get("result")
    except (httpx.HTTPError,ValueError) as exc:raise RuntimeError("Telegram временно недоступен") from exc


async def connect_link(user_id):
    profile=await bot_call("getMe")
    username=profile.get("username","") if isinstance(profile,dict) else ""
    if not re.fullmatch(r"[A-Za-z0-9_]{5,64}",username):raise RuntimeError("Не удалось получить адрес бота")
    settings(user_id);token=secrets.token_urlsafe(24)
    with accounts._connect() as db:
        db.execute("DELETE FROM telegram_links WHERE user_id=? OR expires_at<=?",(user_id,time.time()))
        db.execute("INSERT INTO telegram_links VALUES (?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),user_id,time.time()+600))
    return {"url":f"https://t.me/{username}?start={token}","expires_in":600}


def disconnect(user_id):
    settings(user_id)
    with accounts._connect() as db:
        db.execute("UPDATE notification_settings SET chat_id=NULL,telegram_name=NULL,telegram_enabled=0 WHERE user_id=?",(user_id,))
        db.execute("DELETE FROM telegram_links WHERE user_id=?",(user_id,))


def bind(message):
    if not isinstance(message,dict):return None
    chat=message.get("chat") or {};sender=message.get("from") or {};text=message.get("text","")
    if chat.get("type")!="private" or chat.get("id")!=sender.get("id") or not isinstance(chat.get("id"),int) or isinstance(chat.get("id"),bool) or chat["id"]<=0:return None
    if text=="/stop":
        with accounts._connect() as db:
            schema(db);db.execute("UPDATE notification_settings SET telegram_enabled=0 WHERE chat_id=?",(chat["id"],))
        return "Уведомления отключены. Включить их можно в аккаунте MultiMarket."
    match=re.fullmatch(r"/start(?:@[A-Za-z0-9_]+)? ([A-Za-z0-9_-]{32})",text)
    if not match:return None
    with accounts._connect() as db:
        schema(db);db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM telegram_links WHERE token_hash=? AND expires_at>?",(hashlib.sha256(match[1].encode()).hexdigest(),time.time())).fetchone()
        if not row:return "Ссылка устарела. Создайте новую ссылку в аккаунте MultiMarket."
        other=db.execute("SELECT user_id FROM notification_settings WHERE chat_id=? AND user_id!=?",(chat["id"],row["user_id"])).fetchone()
        if other:return "Этот Telegram уже подключён к другому аккаунту. Сначала отключите его там."
        db.execute("UPDATE notification_settings SET chat_id=?,telegram_name=?,telegram_enabled=1 WHERE user_id=?",(chat["id"],str(sender.get("username") or sender.get("first_name") or "Telegram")[:100],row["user_id"]))
        db.execute("DELETE FROM telegram_links WHERE user_id=?",(row["user_id"],))
    return "Telegram подключён к MultiMarket. Для каждого товара можно настроить цену и каналы уведомлений."


def enqueue(db,alert,monitor):
    schema(db)
    for channel in ("email","telegram"):
        if monitor.get("notify_"+channel):db.execute("INSERT OR IGNORE INTO notification_deliveries(alert_id,channel) VALUES (?,?)",(alert["id"],channel))


def claim():
    with accounts._connect() as db:
        schema(db);db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM notification_deliveries WHERE (status='pending' OR status='sending') AND next_at<=? AND locked_until<=? ORDER BY next_at,alert_id LIMIT 1",(time.time(),time.time())).fetchone()
        if row:db.execute("UPDATE notification_deliveries SET status='sending',locked_until=?,attempts=attempts+1 WHERE alert_id=? AND channel=?",(time.time()+90,row["alert_id"],row["channel"]))
    return dict(row) if row else None


def message_text(alert,monitor):
    if alert.get("reason")=="target":head="Достигнута целевая цена"
    else:head="Цена снизилась" if alert["change_percent"]<0 else "Цена выросла"
    return f"MultiMarket: {head}\n{monitor['title']}\n{alert['new_price']:g} {alert['currency']}\n{monitor['product_url']}"


async def deliver_one(item):
    from . import monitoring
    with accounts._connect() as db:
        alert_row=db.execute("SELECT * FROM price_alerts WHERE id=?",(item["alert_id"],)).fetchone()
    alert=dict(alert_row) if alert_row else None
    monitor=monitoring.get_monitor(alert["monitor_id"]) if alert else None
    outcome="cancelled"
    try:
        if monitor and monitor.get("user_id") and monitor.get("notify_"+item["channel"]):
            user=accounts.get_user(monitor["user_id"]);prefs=settings(monitor["user_id"])
            if user and prefs[item["channel"]+"_enabled"]:
                text=message_text(alert,monitor)
                if item["channel"]=="email" and prefs["email_available"]:
                    await asyncio.to_thread(mailer.send,user["email"],"MultiMarket — изменение цены",text,f"alert-{alert['id']}-{user['id']}");outcome="sent"
                elif item["channel"]=="telegram" and prefs["telegram_connected"]:
                    with accounts._connect() as db:chat=db.execute("SELECT chat_id FROM notification_settings WHERE user_id=?",(user["id"],)).fetchone()[0]
                    await bot_call("sendMessage",chat_id=chat,text=text);outcome="sent"
    except RuntimeError:outcome="failed" if item["attempts"]>=4 else "pending"
    with accounts._connect() as db:
        db.execute("UPDATE notification_deliveries SET status=?,locked_until=0,next_at=? WHERE alert_id=? AND channel=?",(outcome,time.time()+min(3600,60*2**item["attempts"]),item["alert_id"],item["channel"]))


async def delivery_loop(stop):
    while not stop.is_set():
        try:
            for _ in range(20):
                item=claim()
                if not item:break
                await deliver_one(item)
        except Exception:
            logging.getLogger(__name__).warning("Notification worker failed; pending deliveries will be retried")
        try:await asyncio.wait_for(stop.wait(),timeout=15)
        except asyncio.TimeoutError:pass


async def telegram_loop(stop):
    owner=secrets.token_hex(16)
    delay=5
    while not stop.is_set():
        if not os.getenv("MULTIMARKET_TELEGRAM_BOT_TOKEN"):return
        try:
            with accounts._connect() as db:
                schema(db);db.execute("BEGIN IMMEDIATE")
                row=db.execute("SELECT * FROM app_jobs WHERE name='telegram_poll'").fetchone()
                can_poll=not row or row["expires_at"]<time.time() or row["value"]==owner
                if can_poll:db.execute("INSERT INTO app_jobs VALUES ('telegram_poll',?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value,expires_at=excluded.expires_at",(owner,time.time()+45))
                offset=db.execute("SELECT value FROM app_jobs WHERE name='telegram_offset'").fetchone()
            if can_poll:
                updates=await bot_call("getUpdates",offset=int(offset[0]) if offset else 0,timeout=20,allowed_updates=["message"])
                if not isinstance(updates,list):raise ValueError("Invalid updates response")
                for update in updates or []:
                    if not isinstance(update,dict) or not isinstance(update.get("update_id"),int):continue
                    answer=bind(update.get("message"))
                    if answer:
                        try:await bot_call("sendMessage",chat_id=update["message"]["chat"]["id"],text=answer)
                        except RuntimeError:pass
                    with accounts._connect() as db:db.execute("INSERT INTO app_jobs VALUES ('telegram_offset',?,0) ON CONFLICT(name) DO UPDATE SET value=excluded.value",(str(update["update_id"]+1),))
            delay=5
        except (RuntimeError,ValueError,KeyError,sqlite3.Error):
            delay=min(300,delay*2);logging.getLogger(__name__).warning("Telegram polling unavailable; retrying later")
        try:await asyncio.wait_for(stop.wait(),timeout=delay)
        except asyncio.TimeoutError:pass
    with accounts._connect() as db:db.execute("DELETE FROM app_jobs WHERE name='telegram_poll' AND value=?",(owner,))
