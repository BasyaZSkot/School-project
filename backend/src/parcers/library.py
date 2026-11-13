"""Per-account favourites and delivery preferences; snapshots never become trusted prices."""
import hashlib
import json
import math
import re
from urllib.parse import urlparse,parse_qsl,urlencode

from . import accounts
from .regions import get_region

HOSTS = {"Ozon": ("ozon.ru",), "Wildberries": ("wildberries.ru", "wildberries.by", "wildberries.kz"), "Яндекс Маркет": ("market.yandex.ru",)}


def locator(offer):
    url=urlparse(offer["url"])
    params=sorted((k,v) for k,v in parse_qsl(url.query,keep_blank_values=True) if k.casefold() not in {"lr","yclid","gclid","_openstat"} and not k.casefold().startswith("utm_"))
    return (offer["marketplace"],url.path.rstrip("/")+("?"+urlencode(params) if params else ""))


def same_product(left,right):
    for a in left["offers"]:
        for b in right["offers"]:
            if locator(a)!=locator(b):continue
            if a.get("external_id") and b.get("external_id") and a["external_id"]!=b["external_id"]:continue
            av,bv=a.get("variants",{}),b.get("variants",{})
            if all(av[k]==bv[k] for k in av.keys()&bv.keys()):return True
    return False


def init_db():
    with accounts._connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS favorites (
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          id TEXT NOT NULL, snapshot TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY(user_id,id)
        );
        CREATE TABLE IF NOT EXISTS delivery_preferences (
          user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          data TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)


def valid_url(marketplace, value):
    if not isinstance(value, str) or len(value) > 2048: return False
    try:
        p = urlparse(value)
        return p.scheme == "https" and not p.username and not p.password and p.port in (None,443) and any(p.hostname == h or (p.hostname or "").endswith("."+h) for h in HOSTS.get(marketplace,()))
    except ValueError: return False


def snapshot(data):
    if not isinstance(data, dict) or not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("Укажите товар для сохранения")
    offers = []
    for raw in (data.get("offers") or [])[:600]:
        if not isinstance(raw, dict) or not valid_url(raw.get("marketplace"),raw.get("url")): continue
        price = raw.get("price")
        if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price <= 0: continue
        currency = str(raw.get("currency", "RUB")).upper()
        if not re.fullmatch(r"[A-Z]{3}",currency): continue
        offer = {"marketplace": raw["marketplace"], "url":raw["url"], "price":price,"currency":currency,"title":str(raw.get("title") or data["title"])[:300]}
        for key in ("brand","model","seller","condition","external_id"):
            if isinstance(raw.get(key),str): offer[key]=raw[key][:200]
        if isinstance(raw.get("in_stock"),bool): offer["in_stock"]=raw["in_stock"]
        if type(raw.get("rating")) in (int,float) and math.isfinite(raw["rating"]) and 0 < raw["rating"] <= 5: offer["rating"]=raw["rating"]
        if type(raw.get("review_count")) is int and 0 <= raw["review_count"] <= 2**53-1: offer["review_count"]=raw["review_count"]
        images = [raw.get("image_url"),*(raw.get("image_urls") if isinstance(raw.get("image_urls"),list) else [])]
        offer["image_urls"] = []
        for value in images:
            try:
                p=urlparse(value) if isinstance(value,str) and len(value)<2048 else None
                if p and p.scheme=="https" and p.hostname and not p.username and not p.password and value not in offer["image_urls"]: offer["image_urls"].append(value)
            except ValueError: pass
        offer["image_urls"]=offer["image_urls"][:20];offer["image_url"]=next(iter(offer["image_urls"]),None)
        specs=raw.get("specifications") if isinstance(raw.get("specifications"),list) else []
        offer["specifications"]=[{"name":str(s["name"])[:160],"value":str(s["value"])[:500]} for s in specs[:100] if isinstance(s,dict) and s.get("name") and s.get("value")]
        from .variants import extract
        offer["variants"]=extract(offer["title"],offer["specifications"],raw.get("variants"),offer.get("brand"),offer.get("model"),offer.get("condition"))
        offers.append(offer)
    if not offers: raise ValueError("Не удалось сохранить предложения товара")
    # Stable identity is independent of price, order and transient delivery region params.
    def identity_key(o):
        _,path=locator(o)
        return json.dumps([o["marketplace"],path,o.get("external_id") or "",o["variants"]],ensure_ascii=False,sort_keys=True,separators=(",",":"))
    identity=sorted({identity_key(o) for o in offers})
    return {"id":hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:32],"title":data["title"].strip()[:300],"offers":offers}


def favorites(user_id):
    init_db()
    with accounts._connect() as db:
        rows=db.execute("SELECT * FROM favorites WHERE user_id=? ORDER BY updated_at DESC",(user_id,)).fetchall()
    return [{**json.loads(r["snapshot"]),"saved_at":r["updated_at"]} for r in rows]


def save_favorite(user_id, data):
    clean=snapshot(data);init_db()
    with accounts._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for row in db.execute("SELECT id,snapshot FROM favorites WHERE user_id=?",(user_id,)):
            if same_product(clean,json.loads(row["snapshot"])):clean["id"]=row["id"];break
        if db.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?",(user_id,)).fetchone()[0]>=200 and not db.execute("SELECT 1 FROM favorites WHERE user_id=? AND id=?",(user_id,clean["id"])).fetchone(): raise ValueError("В избранном может быть до 200 товаров")
        db.execute("INSERT INTO favorites VALUES (?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET snapshot=excluded.snapshot,updated_at=excluded.updated_at",(user_id,clean["id"],json.dumps(clean,ensure_ascii=False),accounts._now()))
    return clean


def remove_favorite(user_id, item_id):
    init_db()
    with accounts._connect() as db:
        return bool(db.execute("DELETE FROM favorites WHERE user_id=? AND id=?",(user_id,item_id)).rowcount)


def delivery(user_id):
    init_db()
    with accounts._connect() as db:
        row=db.execute("SELECT data FROM delivery_preferences WHERE user_id=?",(user_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_delivery(user_id, data):
    region_id=data.get("region_id");get_region(region_id)
    choices=data.get("choices")
    if not isinstance(choices,dict) or len(choices)>180: raise ValueError("Некорректный список пунктов")
    cleaned={}
    for key,point in choices.items():
        if not isinstance(point,dict): raise ValueError("Некорректный пункт выдачи")
        get_region(point.get("region_id"))
        if not point.get("region_id") or point.get("marketplace") not in HOSTS or key!=str(point["region_id"])+":"+point["marketplace"] or not re.fullmatch(r"osm:[NWR]:[1-9]\d{0,15}",str(point.get("id",""))): raise ValueError("Некорректный пункт выдачи")
        for coord,bound in (("lat",85),("lon",180)):
            v=point.get(coord)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>bound: raise ValueError("Некорректные координаты")
        if not isinstance(point.get("address"),str) or not 1<=len(point["address"])<=500: raise ValueError("Некорректный адрес")
        cleaned[key]={k:point[k] for k in ("id","marketplace","region_id","address","lat","lon")};cleaned[key]["name"]=str(point.get("name",point["marketplace"]))[:200]
    clean={"region_id":region_id,"choices":cleaned};init_db()
    with accounts._connect() as db:
        db.execute("INSERT INTO delivery_preferences VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",(user_id,json.dumps(clean,ensure_ascii=False),accounts._now()))
    return clean
