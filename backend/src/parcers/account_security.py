"""Hashed, purpose-bound, expiring and single-use account action tokens."""
import hashlib
import re
import secrets
import time
from . import accounts


def init_db(db):
    db.execute("""CREATE TABLE IF NOT EXISTS account_tokens (
      token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      purpose TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL)""")


def issue(user_id, purpose):
    if purpose not in {"reset","verify"}: raise ValueError("Неизвестное действие")
    token=secrets.token_urlsafe(32);now=time.time()
    with accounts._connect() as db:
        init_db(db);db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM account_tokens WHERE expires_at<=?",(now,))
        last=db.execute("SELECT created_at FROM account_tokens WHERE user_id=? AND purpose=?",(user_id,purpose)).fetchone()
        if last and last["created_at"]>now-60: raise ValueError("Новое письмо можно запросить через минуту")
        db.execute("DELETE FROM account_tokens WHERE user_id=? AND purpose=?",(user_id,purpose))
        db.execute("INSERT INTO account_tokens VALUES (?,?,?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),user_id,purpose,now,now+(1800 if purpose=="reset" else 86400)))
    return token


def local_user(email):
    with accounts._connect() as db:
        return accounts._to_dict(db.execute("SELECT * FROM users WHERE provider='local' AND subject=?",(email.strip().lower(),)).fetchone())


def consume(token,purpose,password=None):
    if not isinstance(token,str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}",token): raise ValueError("Ссылка недействительна или срок её действия истёк")
    if purpose=="reset" and (not isinstance(password,str) or not 8<=len(password)<=128): raise ValueError("Пароль должен содержать от 8 до 128 символов")
    encoded=None
    if purpose=="reset":
        salt=secrets.token_hex(16);encoded=salt+":"+accounts._password_hash(password,salt)
    with accounts._connect() as db:
        init_db(db);db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT * FROM account_tokens WHERE token_hash=? AND purpose=? AND expires_at>?",(hashlib.sha256(token.encode()).hexdigest(),purpose,time.time())).fetchone()
        if not row: raise ValueError("Ссылка недействительна или срок её действия истёк")
        if purpose=="reset":
            updated=db.execute("UPDATE users SET password_hash=?,auth_version=auth_version+1 WHERE id=? AND provider='local'",(encoded,row["user_id"]))
            if not updated.rowcount: raise ValueError("Для этого аккаунта используйте вход через провайдера")
            db.execute("DELETE FROM account_tokens WHERE user_id=?",(row["user_id"],))
        else:
            db.execute("UPDATE users SET email_verified=1 WHERE id=?",(row["user_id"],))
            db.execute("DELETE FROM account_tokens WHERE user_id=? AND purpose='verify'",(row["user_id"],))
    return row["user_id"]
