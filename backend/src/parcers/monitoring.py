from __future__ import annotations

from contextlib import contextmanager
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("MULTIMARKET_DB_PATH", str(BACKEND_DIR / "data" / "multimarket.sqlite3")))


def _now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with _connect() as db:
        columns = [r["name"] for r in db.execute("PRAGMA table_info(monitors)")]
        if columns and "user_id" not in columns:
            schema = db.execute("SELECT sql FROM sqlite_master WHERE name = 'monitors'").fetchone()[0]
            schema = schema.replace("CREATE TABLE monitors", "CREATE TABLE monitors_new", 1)
            schema = schema.replace("UNIQUE(product_url)", "user_id TEXT, UNIQUE(user_id, product_url)")
            db.execute("PRAGMA foreign_keys = OFF")
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute(schema)
                names = ", ".join(columns)
                db.execute(f"INSERT INTO monitors_new ({names}) SELECT {names} FROM monitors")
                db.execute("DROP TABLE monitors")
                db.execute("ALTER TABLE monitors_new RENAME TO monitors")
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS monitors (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            product_url TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            title TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            current_price REAL,
            currency TEXT,
            last_checked_at TEXT,
            next_run_at TEXT NOT NULL,
            last_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            user_id TEXT,
            UNIQUE(user_id, product_url)
        );
        CREATE INDEX IF NOT EXISTS idx_monitors_user ON monitors(user_id);
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
            price REAL NOT NULL,
            currency TEXT NOT NULL,
            captured_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_monitor_time
            ON price_snapshots(monitor_id, captured_at);
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
            old_price REAL NOT NULL,
            new_price REAL NOT NULL,
            currency TEXT NOT NULL,
            change_percent REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        """)


def create_monitor(*, query: str, product_url: str, marketplace: str, title: str,
                   interval_seconds: int, user_id: str | None = None) -> dict[str, Any]:
    now = _now()
    monitor_id = str(uuid.uuid4())
    with _connect() as db:
        db.execute(
            """INSERT INTO monitors
            (id, query, product_url, marketplace, title, interval_seconds,
             active, next_run_at, last_status, created_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'pending', ?, ?)""",
            (monitor_id, query, product_url, marketplace, title, interval_seconds,
             now.isoformat(), now.isoformat(), user_id),
        )
        row = db.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    return _monitor_dict(row)


def _monitor_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["active"] = bool(result["active"])
    return result


def list_monitors(user_id: str | None = None) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute("SELECT * FROM monitors" + (" WHERE user_id = ?" if user_id is not None else "") + " ORDER BY created_at DESC", (user_id,) if user_id is not None else ()).fetchall()
    return [_monitor_dict(row) for row in rows]


def get_monitor(monitor_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM monitors WHERE id = ?" + (" AND user_id = ?" if user_id is not None else ""), (monitor_id, user_id) if user_id is not None else (monitor_id,)).fetchone()
    return _monitor_dict(row) if row else None


def update_monitor(monitor_id: str, *, user_id: str | None = None, active: bool | None = None,
                   interval_seconds: int | None = None) -> dict[str, Any] | None:
    assignments, values = [], []
    if active is not None:
        assignments.append("active = ?")
        values.append(int(active))
    if interval_seconds is not None:
        assignments.extend(["interval_seconds = ?", "next_run_at = ?"])
        values.extend([interval_seconds, _now().isoformat()])
    if assignments:
        values.append(monitor_id)
        with _connect() as db:
            if user_id is not None:
                values.append(user_id)
            db.execute(f"UPDATE monitors SET {', '.join(assignments)} WHERE id = ?" + (" AND user_id = ?" if user_id is not None else ""), values)
    return get_monitor(monitor_id, user_id)


def delete_monitor(monitor_id: str, user_id: str | None = None) -> bool:
    with _connect() as db:
        cursor = db.execute("DELETE FROM monitors WHERE id = ?" + (" AND user_id = ?" if user_id is not None else ""), (monitor_id, user_id) if user_id is not None else (monitor_id,))
    return cursor.rowcount > 0


def due_monitors(limit: int = 25) -> list[dict[str, Any]]:
    now = _now().isoformat()
    with _connect() as db:
        rows = db.execute(
            """SELECT * FROM monitors
            WHERE active = 1 AND next_run_at <= ? AND user_id IS NOT NULL
            ORDER BY next_run_at LIMIT ?""",
            (now, limit),
        ).fetchall()
    return [_monitor_dict(row) for row in rows]


def record_check(monitor_id: str, *, price: float | None, currency: str | None,
                 status: str, alert_threshold_percent: float = 10.0) -> dict[str, Any] | None:
    now = _now()
    alert_data = None
    with _connect() as db:
        row = db.execute(
            "SELECT current_price, currency, interval_seconds FROM monitors WHERE id = ?",
            (monitor_id,),
        ).fetchone()
        if row is None:
            return None
        if price is not None and currency:
            previous = row["current_price"]
            previous_currency = row["currency"]
            db.execute(
                """INSERT INTO price_snapshots(monitor_id, price, currency, captured_at)
                VALUES (?, ?, ?, ?)""",
                (monitor_id, price, currency, now.isoformat()),
            )
            if previous is not None and previous_currency == currency and previous > 0:
                change = (price - previous) / previous * 100
                if abs(change) >= alert_threshold_percent:
                    cursor = db.execute(
                        """INSERT INTO price_alerts
                        (monitor_id, old_price, new_price, currency, change_percent, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (monitor_id, previous, price, currency, change, now.isoformat()),
                    )
                    alert_data = {
                        "id": cursor.lastrowid, "monitor_id": monitor_id,
                        "old_price": previous, "new_price": price,
                        "currency": currency, "change_percent": change,
                        "created_at": now.isoformat(),
                    }
            db.execute(
                """UPDATE monitors SET current_price = ?, currency = ?, last_checked_at = ?,
                next_run_at = ?, last_status = ? WHERE id = ?""",
                (price, currency, now.isoformat(),
                 (now + timedelta(seconds=row["interval_seconds"])).isoformat(),
                 status, monitor_id),
            )
        else:
            db.execute(
                """UPDATE monitors SET last_checked_at = ?, next_run_at = ?, last_status = ?
                WHERE id = ?""",
                (now.isoformat(),
                 (now + timedelta(seconds=row["interval_seconds"])).isoformat(),
                 status, monitor_id),
            )
    return alert_data


async def send_telegram_alert(alert: dict[str, Any], monitor: dict[str, Any]) -> None:
    """Send opt-in price alerts; credentials stay in server environment."""
    token = os.getenv("MULTIMARKET_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("MULTIMARKET_TELEGRAM_CHAT_ID")
    if monitor.get("user_id") or not token or not chat_id:
        return
    import httpx

    direction = "снизилась" if alert["change_percent"] < 0 else "выросла"
    message = (
        f"MultiMarket: цена товара «{monitor['title']}» {direction} на "
        f"{abs(alert['change_percent']):.1f}%\n"
        f"{alert['old_price']:.2f} → {alert['new_price']:.2f} {alert['currency']}\n"
        f"{monitor['product_url']}"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return


def price_history(monitor_id: str, limit: int = 500) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            """SELECT price, currency, captured_at FROM price_snapshots
            WHERE monitor_id = ? ORDER BY captured_at DESC LIMIT ?""",
            (monitor_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def list_alerts(monitor_id: str | None = None, limit: int = 100, user_id: str | None = None) -> list[dict[str, Any]]:
    conditions, values = [], []
    if monitor_id:
        conditions.append("a.monitor_id = ?")
        values.append(monitor_id)
    if user_id is not None:
        conditions.append("m.user_id = ?")
        values.append(user_id)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with _connect() as db:
        rows = db.execute("SELECT a.* FROM price_alerts a JOIN monitors m ON m.id = a.monitor_id" + where + " ORDER BY a.created_at DESC LIMIT ?", (*values, limit)).fetchall()
    return [dict(row) for row in rows]


async def monitoring_loop(search_service, stop_event, interval_seconds: int = 30) -> None:
    import asyncio

    while not stop_event.is_set():
        for monitor in due_monitors():
            try:
                matched = None
                parse_product = getattr(search_service, "parse_product", None)
                if callable(parse_product):
                    try:
                        parsed_offer = await parse_product(
                            monitor["marketplace"], monitor["product_url"]
                        )
                    except Exception:
                        parsed_offer = None
                    if parsed_offer is not None:
                        matched = {
                            "price": parsed_offer.price,
                            "currency": parsed_offer.currency,
                        }

                if matched is None:
                    result = await search_service.search(monitor["query"], limit=50)
                    matched = next(
                        (offer for provider in result["providers"]
                         for offer in provider.get("offers", [])
                         if offer.get("url") == monitor["product_url"]
                         and offer.get("marketplace") == monitor["marketplace"]),
                        None,
                    )
                if matched:
                    alert = record_check(
                        monitor["id"], price=float(matched["price"]),
                        currency=matched["currency"], status="ok",
                    )
                    if alert:
                        await send_telegram_alert(alert, monitor)
                else:
                    record_check(monitor["id"], price=None, currency=None, status="offer_not_returned")
            except Exception:
                record_check(monitor["id"], price=None, currency=None, status="source_error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
