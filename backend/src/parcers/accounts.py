"""Small SQLite-backed account store for OAuth identities."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
import hashlib
import hmac
import re
import secrets
import time
import uuid
from typing import Any, Iterator

from . import monitoring


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    monitoring.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(monitoring.DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            subject TEXT NOT NULL,
            email TEXT,
            name TEXT NOT NULL,
            picture_url TEXT,
            role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
            created_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL,
            UNIQUE(provider, subject)
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE TABLE IF NOT EXISTS oauth_transactions (
            state TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            verifier TEXT NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_attempts (
            key TEXT NOT NULL,
            attempted_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_auth_attempts ON auth_attempts(key, attempted_at);
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        if "password_hash" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "email_verified" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        if "auth_version" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with _connect():
        pass


def _password_hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                          n=16384, r=8, p=1).hex()


def allow_auth_attempt(email: str, address: str) -> bool:
    now = time.time()
    keys = ["email:" + email.strip().lower(), "ip:" + address]
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM auth_attempts WHERE attempted_at < ?", (now - 900,))
        for key, limit in zip(keys, (10, 50)):
            if db.execute("SELECT COUNT(*) FROM auth_attempts WHERE key = ?", (key,)).fetchone()[0] >= limit:
                return False
        db.executemany("INSERT INTO auth_attempts VALUES (?, ?)", [(key, now) for key in keys])
    return True


def register_user(*, email: str, password: str, name: str) -> dict[str, Any]:
    email = email.strip().lower()
    name = name.strip()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Укажите корректный email")
    if not name or len(name) > 160:
        raise ValueError("Укажите имя длиной до 160 символов")
    if not 8 <= len(password) <= 128:
        raise ValueError("Пароль должен содержать от 8 до 128 символов")
    salt = secrets.token_hex(16)
    encoded = salt + ":" + _password_hash(password, salt)
    now = _now()
    user_id = str(uuid.uuid4())
    with _connect() as db:
        try:
            db.execute(
                """INSERT INTO users
                (id, provider, subject, email, name, role, created_at, last_login_at, password_hash)
                VALUES (?, 'local', ?, ?, ?, 'user', ?, ?, ?)""",
                (user_id, email, email, name, now, now, encoded),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Аккаунт с этим email уже зарегистрирован") from exc
        return _to_dict(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()) or {}


def authenticate_user(*, email: str, password: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM users WHERE provider = 'local' AND subject = ?",
                         (email.strip().lower(),)).fetchone()
        # Perform the same expensive calculation for unknown addresses.
        encoded = row["password_hash"] if row else None
        salt, expected = encoded.split(":") if encoded else ("00" * 16, "00" * 64)
        actual = _password_hash(password, salt)
        if not hmac.compare_digest(expected, actual) or row is None:
            return None
        db.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), row["id"]))
        return _to_dict(db.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())


def save_oauth_transaction(*, state: str, provider: str, verifier: str) -> None:
    now = time.time()
    with _connect() as db:
        db.execute("DELETE FROM oauth_transactions WHERE expires_at <= ?", (now,))
        db.execute(
            "INSERT INTO oauth_transactions (state, provider, verifier, expires_at) VALUES (?, ?, ?, ?)",
            (state, provider, verifier, now + 600),
        )


def consume_oauth_transaction(*, state: str, provider: str) -> str | None:
    now = time.time()
    with _connect() as db:
        row = db.execute(
            "SELECT provider, verifier, expires_at FROM oauth_transactions WHERE state = ?",
            (state,),
        ).fetchone()
        db.execute("DELETE FROM oauth_transactions WHERE state = ? OR expires_at <= ?", (state, now))
        if row is None or row["provider"] != provider or row["expires_at"] <= now:
            return None
        return str(row["verifier"])


def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "provider": row["provider"],
        "email": row["email"],
        "name": row["name"],
        "picture_url": row["picture_url"],
        "role": row["role"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
        "email_verified": bool(row["email_verified"]),
        "auth_version": row["auth_version"],
    }


def login_user(
    *,
    provider: str,
    subject: str,
    email: str | None,
    name: str | None,
    picture_url: str | None,
    admin_emails: set[str],
    email_verified: bool = False,
) -> dict[str, Any]:
    provider = provider.strip().lower()
    subject = subject.strip()
    email = email.strip().lower() if email and email.strip() else None
    name = (name or "Пользователь").strip()[:160] or "Пользователь"
    picture_url = picture_url.strip()[:2048] if picture_url else None
    if provider not in {"google", "yandex"} or not subject:
        raise ValueError("OAuth identity is missing required fields")

    now = _now()
    requested_admin = email in admin_emails if email else False
    with _connect() as db:
        row = db.execute(
            "SELECT * FROM users WHERE provider = ? AND subject = ?",
            (provider, subject),
        ).fetchone()
        if row is None:
            user_id = str(uuid.uuid4())
            role = "admin" if requested_admin else "user"
            db.execute(
                """INSERT INTO users
                   (id, provider, subject, email, name, picture_url, role, created_at, last_login_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, provider, subject, email, name, picture_url, role, now, now),
            )
        else:
            user_id = row["id"]
            if row["email"] != email:
                db.execute("UPDATE users SET email_verified=0 WHERE id=?", (user_id,))
                # A link delivered to the old mailbox cannot verify a new address.
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_tokens'").fetchone():
                    db.execute("DELETE FROM account_tokens WHERE user_id=?", (user_id,))
            role = "admin" if requested_admin else row["role"]
            db.execute(
                """UPDATE users SET email = ?, name = ?, picture_url = ?, role = ?, last_login_at = ?
                   WHERE id = ?""",
                (email, name, picture_url, role, now, user_id),
            )
        if email_verified and email:
            db.execute("UPDATE users SET email_verified=1 WHERE id=?",(user_id,))
        return _to_dict(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()) or {}


def get_user(user_id: str | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    with _connect() as db:
        return _to_dict(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def list_users() -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            """SELECT * FROM users
               ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, created_at, email"""
        ).fetchall()
        return [_to_dict(row) or {} for row in rows]


def set_role(user_id: str, role: str) -> dict[str, Any] | None:
    if role not in {"user", "admin"}:
        raise ValueError("Role must be user or admin")
    with _connect() as db:
        cursor = db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if cursor.rowcount == 0:
            return None
        return _to_dict(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def admin_count() -> int:
    with _connect() as db:
        row = db.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'").fetchone()
        return int(row["total"])
