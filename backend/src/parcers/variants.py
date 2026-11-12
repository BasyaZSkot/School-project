"""Conservative variant extraction: absence of a value is never a guessed match."""
import json
import re
import unicodedata


def norm(value):
    return " ".join(re.sub(r"[^0-9a-zа-я]+", " ", unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")).split())


COLORS = {"черный":"чёрный", "black":"чёрный", "белый":"белый", "white":"белый", "silver":"серебристый", "серебристый":"серебристый",
          "gray":"серый", "grey":"серый", "серый":"серый", "blue":"синий", "синий":"синий", "голубой":"голубой", "green":"зелёный", "зеленый":"зелёный",
          "red":"красный", "красный":"красный", "pink":"розовый", "розовый":"розовый", "purple":"фиолетовый", "фиолетовый":"фиолетовый",
          "gold":"золотой", "золотой":"золотой", "graphite":"графитовый", "графитовый":"графитовый", "beige":"бежевый", "бежевый":"бежевый"}


def capacity(value):
    match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(тб|tb|гб|gb|мб|mb)\b", str(value).casefold())
    if not match:
        return None
    number = float(match[1].replace(",", ".")) * (1024 if match[2] in {"тб", "tb"} else 1 / 1024 if match[2] in {"мб", "mb"} else 1)
    return f"{number:g} ГБ"


def extract(title, specifications=None, explicit=None, brand=None, model=None, condition=None):
    result = {}
    explicit = explicit if isinstance(explicit, dict) else {}
    for key in ("storage", "ram", "color", "package", "condition", "version"):
        value = str(explicit.get(key) or "").strip()[:160]
        if value:
            result[key] = capacity(value) if key in {"storage", "ram"} else norm(value)
            if result[key] is None:
                result.pop(key)
    for item in (specifications or [])[:100]:
        if not isinstance(item, dict):
            continue
        name, value = norm(item.get("name")), str(item.get("value") or "").strip()[:160]
        key = None
        if name in {"цвет", "цвет товара", "color"}: key = "color"
        elif "оперативн" in name or name == "ram": key = "ram"
        elif name in {"память", "объем памяти", "storage", "storage capacity"} or "встроенн" in name and "памят" in name: key = "storage"
        elif name in {"комплектация", "комплект поставки", "package"}: key = "package"
        elif name in {"состояние", "condition"}: key = "condition"
        elif name in {"версия", "региональная версия"}: key = "version"
        if key and value:
            parsed = capacity(value) if key in {"storage", "ram"} else norm(value)
            if parsed: result[key] = parsed
    text = norm(title)
    # Remove brand/model words before looking for ambiguous colour names.
    rest = text
    for value in (brand, model):
        if value: rest = rest.replace(norm(value), " ")
    pair = re.search(r"\b(\d{1,3})\s*[/+]\s*(\d{2,4})\s*(?:gb|гб)\b", str(title).casefold())
    if pair:
        result.setdefault("ram", pair[1] + " ГБ"); result.setdefault("storage", pair[2] + " ГБ")
    elif "storage" not in result:
        matches = re.findall(r"\b\d+(?:[.,]\d+)?\s*(?:gb|гб|tb|тб)\b", str(title).casefold())
        if len(matches) == 1: result["storage"] = capacity(matches[0])
    colors = {color for word, color in COLORS.items() if re.search(r"\b" + re.escape(word) + r"\b", rest)}
    if len(colors) == 1: result.setdefault("color", colors.pop())
    if result.get("color"):
        result["color"] = COLORS.get(norm(result["color"]), norm(result["color"]))
    state = norm(condition) or result.get("condition") or text
    if re.search(r"\b(восстановленный|восстановлен|refurbished|refurb)\b", state): result["condition"] = "восстановленный"
    elif re.search(r"\b(б у|бу|used|бывший в употреблении)\b", state): result["condition"] = "б/у"
    elif re.search(r"\b(новый|новое|new)\b", state): result["condition"] = "новый"
    elif condition: result["condition"] = norm(condition)[:160]
    return {key:value for key,value in sorted(result.items()) if value}


def signature(offer):
    return json.dumps(extract(offer.title, offer.specifications, offer.variants, offer.brand, offer.model, offer.condition), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
