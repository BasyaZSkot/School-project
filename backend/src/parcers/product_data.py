"""Bounded normalization of product media and published delivery estimates."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import re
from urllib.parse import urljoin, urlparse

MAX_IMAGES = 20
MAX_REVIEWS = 100
MAX_SPECIFICATIONS = 100


def image_urls(value, base_url: str = "") -> list[str]:
    result = []

    def visit(item, depth=0):
        if depth > 4 or len(result) >= MAX_IMAGES:
            return
        if isinstance(item, list):
            for child in item[:100]:
                visit(child, depth + 1)
        elif isinstance(item, dict):
            for key in ("url", "contentUrl", "src", "original", "imageUrl"):
                if item.get(key):
                    visit(item[key], depth + 1)
                    break
        elif isinstance(item, str):
            try:
                url = urljoin(base_url, item.strip().lstrip("\u200b"))
                parsed = urlparse(url)
            except ValueError:
                return
            if (parsed.scheme == "https" and parsed.hostname and not parsed.username
                    and not parsed.password and len(url) <= 2048 and url not in result):
                result.append(url)

    visit(value)
    return result


def _days(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return math.ceil(number) if math.isfinite(number) and 0 <= number <= 365 else None
    except (ValueError, TypeError):
        return None


def _delivery_dates(text: str, reference: date) -> dict:
    text = " ".join(text.casefold().replace("ё", "е").split())
    relative = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
    days = [offset for word, offset in relative.items() if re.search(r"\b" + word + r"\b", text)]
    if days:
        return {"earliest_date": (reference + timedelta(days=min(days))).isoformat(),
                "latest_date": (reference + timedelta(days=max(days))).isoformat()}
    dash = r"[-–—‐‑‒−]"
    duration = re.search(r"\b(\d{1,3})(?:\s*" + dash + r"\s*(\d{1,3}))?\s*(?:дн(?:я|ей|ь|\.)?|суток)\b", text)
    if duration:
        lo, hi = int(duration[1]), int(duration[2] or duration[1])
        if 0 <= lo <= hi <= 365:
            return {"min_days": lo, "max_days": hi}
    months = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5,
              "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
    matches = list(re.finditer(r"\b(\d{1,2})(?:\s*" + dash + r"\s*(\d{1,2}))?\s+(" + "|".join(months) + r")[а-я]*\.?\s*(\d{4})?", text))
    if not matches:
        return {}
    match = matches[0]
    lo, hi, month = int(match[1]), int(match[2] or match[1]), months[match[3]]
    year = int(match[4]) if match[4] else reference.year + (reference.month == 12 and month <= 2)
    try:
        earliest, latest = date(year, month, lo), date(year, month, hi)
    except ValueError:
        return {}
    if len(matches) > 1 and re.fullmatch(r"\s*" + dash + r"\s*", text[match.end():matches[1].start()]):
        end = matches[1]
        end_month = months[end[3]]
        end_year = int(end[4]) if end[4] else year + (month == 12 and end_month == 1)
        try:
            latest = date(end_year, end_month, int(end[2] or end[1]))
        except ValueError:
            return {}
    if earliest > latest:
        return {}
    # "С 15 ноября" supplies a start, not a latest-arrival promise.
    if re.search(r"\b(?:с|от|не раньше)\s+" + re.escape(match[0]), text) and not match[2]:
        return {"earliest_date": earliest.isoformat()}
    return {"earliest_date": earliest.isoformat(), "latest_date": latest.isoformat()}


def delivery_data(value, *, reference_date: date | None = None) -> dict:
    """Accept explicit feed estimates; never infer a promise from a product price."""
    if isinstance(value, str):
        text = " ".join(value.split())[:240]
        value = {"text": text} if text else {}
    if not isinstance(value, dict):
        return {}
    result = {}
    region_id = value.get("region_id")
    if isinstance(region_id, int) and not isinstance(region_id, bool) and 0 < region_id <= 1000000:
        result["region_id"] = region_id
    if value.get("partial") is True:
        result["partial"] = True
    for key in ("text", "destination", "method"):
        if isinstance(value.get(key), str) and value[key].strip():
            result[key] = " ".join(value[key].split())[:240]
    for key in ("min_days", "max_days"):
        number = _days(value.get(key))
        if number is not None:
            result[key] = number
    if result.get("min_days", 0) > result.get("max_days", 365):
        result.pop("min_days", None)
        result.pop("max_days", None)
    for key in ("earliest_date", "latest_date"):
        try:
            result[key] = date.fromisoformat(str(value[key])).isoformat()
        except (KeyError, ValueError, TypeError):
            pass
    if result.get("earliest_date", "") > result.get("latest_date", "9999"):
        result.pop("earliest_date", None)
        result.pop("latest_date", None)
    if result.get("text") and not result.get("partial") and not (result.get("earliest_date") or result.get("latest_date")):
        reference = reference_date or datetime.now(timezone(timedelta(hours=3))).date()
        inferred = _delivery_dates(result["text"], reference)
        for key, val in inferred.items():
            result.setdefault(key, val)
        if inferred:
            result["observed_on"] = reference.isoformat()
    try:
        amount = float(value["cost"])
        currency = str(value.get("currency") or "").upper()
        if math.isfinite(amount) and amount >= 0 and len(currency) == 3 and currency.isalpha():
            result.update(cost=amount, currency=currency)
    except (KeyError, TypeError, ValueError):
        pass
    return result


def schema_delivery(offer: dict) -> dict:
    entries = offer.get("shippingDetails")
    entries = entries if isinstance(entries, list) else [entries]
    # Do not combine windows belonging to different delivery destinations.
    for entry in entries[:20]:
        if not isinstance(entry, dict):
            continue
        raw = {}
        timing = entry.get("deliveryTime")
        if isinstance(timing, dict):
            periods = [timing.get("handlingTime"), timing.get("transitTime")]
            periods = [p for p in periods if isinstance(p, dict)]
            valid = [p for p in periods if str(p.get("unitCode") or p.get("unitText") or "").casefold()
                     in {"day", "days", "d", "день", "дня", "дней"}]
            if valid and len(valid) == len(periods):
                for key, field in (("min_days", "minValue"), ("max_days", "maxValue")):
                    values = [_days(p.get(field, p.get("value"))) for p in valid]
                    if all(n is not None for n in values):
                        raw[key] = sum(values)
                if len(periods) != 2:
                    maximum = raw.pop("max_days", None)
                    raw.pop("min_days", None)
                    if maximum is not None:
                        label = "В пути" if isinstance(timing.get("transitTime"), dict) else "Подготовка к отправке"
                        raw["text"] = f"{label}: до {maximum} дн. Полный срок — в магазине."
                        raw["partial"] = True
        region = entry.get("shippingDestination")
        if isinstance(region, dict):
            raw["destination"] = region.get("addressRegion") or region.get("addressCountry")
        rate = entry.get("shippingRate")
        if isinstance(rate, dict):
            raw.update(cost=rate.get("value"), currency=rate.get("currency"))
        normalized = delivery_data(raw)
        if normalized:
            return normalized
    return {}
