"""Extract marketplace product state already present in public HTML.

The parser reads JSON documents and JSON-valued state assignments from ordinary
public page scripts. It never evaluates JavaScript or makes follow-up requests.
"""
from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .base import Offer
from .public_html import _clean_description, _number, _price_from_offer, _review_total
from .wb_adapter import wb_record_to_offer
from .product_data import MAX_REVIEWS, MAX_SPECIFICATIONS, image_urls


class _StateScriptParser(HTMLParser):
    """Collect script contents; JavaScript is inspected as text, never executed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture = False
        self._parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "script":
            self._capture = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capture:
            value = "".join(self._parts).strip()
            if value:
                self.documents.append(value)
            self._capture = False
            self._parts = []


_STATE_ASSIGNMENT = re.compile(
    r"(?:window\s*\.\s*)?"
    r"(?:__INITIAL_STATE__|__PRELOADED_STATE__|__NEXT_DATA__|__NUXT__|__APP_STATE__)"
    r"\s*=\s*",
    re.IGNORECASE,
)


def _json_value_at(source: str, start: int) -> Any | None:
    """Decode one object/array literal with a small string-aware bracket scanner."""
    while start < len(source) and source[start].isspace():
        start += 1
    if start >= len(source) or source[start] not in "{[":
        return None
    opening = source[start]
    closing = "}" if opening == "{" else "]"
    stack = [closing]
    in_string = False
    escaped = False
    for index in range(start + 1, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                try:
                    return json.loads(source[start:index + 1])
                except (json.JSONDecodeError, TypeError):
                    return None
    return None


def embedded_json_documents(html: str) -> list[Any]:
    """Return JSON payloads embedded in script tags, including common state assignments."""
    parser = _StateScriptParser()
    parser.feed(html)
    parser.close()
    documents: list[Any] = []
    seen: set[str] = set()
    for raw in parser.documents:
        candidates: list[Any] = []
        try:
            candidates.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            pass
        for match in _STATE_ASSIGNMENT.finditer(raw):
            value = _json_value_at(raw, match.end())
            if value is not None:
                candidates.append(value)
        for value in candidates:
            fingerprint = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
            if fingerprint not in seen:
                seen.add(fingerprint)
                documents.append(value)
    return documents


def _nodes(value: Any, depth: int = 0):
    """Walk JSON objects and decode JSON strings used as nested state values."""
    if depth > 7:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child, depth + 1)
    elif isinstance(value, str):
        stripped = value.strip()
        if len(stripped) > 1 and stripped[0] in "{[":
            try:
                decoded = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                return
            yield from _nodes(decoded, depth + 1)


def extract_wildberries_embedded(html: str, limit: int) -> list[Offer]:
    """Read WB products only from data embedded in the public page."""
    offers: list[Offer] = []
    seen: set[str] = set()
    for document in embedded_json_documents(html):
        for node in _nodes(document):
            products = node.get("products")
            if not isinstance(products, list):
                continue
            for product in products:
                if not isinstance(product, dict):
                    continue
                offer = wb_record_to_offer(product)
                if offer is None or offer.url in seen:
                    continue
                seen.add(offer.url)
                offers.append(offer)
                if len(offers) >= limit:
                    return offers
    return offers


def _first_text(value: Any, preferred_keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for child in value.values():
            found = _first_text(child, preferred_keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_text(child, preferred_keys)
            if found:
                return found
    return None


def _ozon_title(card: dict) -> str | None:
    main_state = card.get("mainState")
    if isinstance(main_state, list):
        for state in main_state:
            if not isinstance(state, dict) or state.get("id") != "name":
                continue
            text_state = state.get("textDS")
            if isinstance(text_state, dict):
                title = text_state.get("text")
                if isinstance(title, str) and title.strip():
                    return title.strip()
    return _first_text(card, ("title", "name"))


def _ozon_price(card: dict) -> float | None:
    main_state = card.get("mainState")
    if not isinstance(main_state, list):
        return None
    price_block = next(
        (state.get("priceV2") for state in main_state
         if isinstance(state, dict) and state.get("type") == "priceV2"),
        None,
    )
    prices = price_block.get("price", []) if isinstance(price_block, dict) else []
    active = next(
        (item.get("text") for item in prices
         if isinstance(item, dict) and item.get("textStyle") == "PRICE"),
        None,
    )
    if not isinstance(active, str):
        return None
    digits = re.sub(r"[^\d]", "", active)
    try:
        value = float(digits)
    except ValueError:
        return None
    return value if value > 0 else None


def _ozon_link(card: dict) -> str | None:
    for node in _nodes(card):
        action = node.get("action")
        if isinstance(action, dict) and isinstance(action.get("link"), str):
            return action["link"]
    return None


def _ozon_image(card: dict) -> str | None:
    for node in _nodes(card):
        for key in ("src", "image", "imageUrl", "url"):
            value = node.get(key)
            if not isinstance(value, str) or not value.startswith("https://"):
                continue
            host = (urlparse(value).hostname or "").lower()
            if "ozon" in host and any(part in value.lower() for part in (".jpg", ".jpeg", ".png", ".webp", "image")):
                return value
    return None


def _ozon_sku(card: dict) -> str | None:
    for node in _nodes(card):
        value = node.get("sku")
        if value not in (None, "") and isinstance(value, (str, int)):
            return str(value)
    return None


def _ozon_sku_from_url(url: str) -> str | None:
    match = re.search(r"-(\d+)/?$", url) or re.search(r"(\d{6,})", url)
    return match.group(1) if match else None


def _ozon_widget_price(value: Any) -> float | None:
    if isinstance(value, (dict, list)):
        value = _first_text(value, ("text", "price", "value"))
    return _price_from_offer({"price": value})


def _ozon_named_scalar(value: Any, keys: tuple[str, ...]) -> Any | None:
    wanted = {key.lower() for key in keys}
    for node in _nodes(value):
        for key, candidate in node.items():
            if str(key).lower() in wanted and isinstance(candidate, (str, int, float)):
                if str(candidate).strip():
                    return candidate
    return None


def _ozon_plain_text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("text") or value.get("description") or value.get("html") or value.get("value")
    if not isinstance(value, str):
        return None
    return _clean_description(re.sub(r"<[^>]+>", " ", unescape(value)))


def _ozon_characteristics(widget: dict) -> list[dict[str, str]]:
    sections = widget.get("characteristics") or []
    if isinstance(sections, dict):
        sections = [sections]
    if not isinstance(sections, list):
        return []
    result = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        items = []
        for key in ("short", "full"):
            values = section.get(key) or []
            if isinstance(values, dict):
                values = [values]
            if isinstance(values, list):
                items.extend(values)
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            values = item.get("values", [])
            if isinstance(values, list):
                value = ", ".join(
                    str(entry.get("text", "")).strip()
                    for entry in values if isinstance(entry, dict) and entry.get("text")
                )
            else:
                value = str(values).strip()
            if name and value:
                result.append({"name": str(name).strip()[:120], "value": value[:500]})
            if len(result) >= MAX_SPECIFICATIONS:
                return result
    return result


def _ozon_review_entries(widget: dict) -> list[dict[str, str]]:
    reviews = []
    seen = set()
    for node in _nodes(widget):
        body = next(
            (node.get(key) for key in ("reviewBody", "body", "content", "text")
             if isinstance(node.get(key), str) and node.get(key).strip()),
            None,
        )
        body = _ozon_plain_text(body)
        if not body or body in seen:
            continue
        author = _first_text(node.get("author") or node.get("user") or {}, ("name", "title"))
        raw_rating = _ozon_named_scalar(node, ("ratingValue", "reviewRating", "rating"))
        rating = _number(raw_rating)
        reviews.append({
            "body": body[:4000],
            "author": author[:120] if author else "Покупатель",
            "date": str(node.get("datePublished") or node.get("date") or "")[:40],
            "rating": str(rating) if rating is not None and rating <= 5 else "",
        })
        seen.add(body)
        if len(reviews) >= MAX_REVIEWS:
            break
    return reviews


def extract_ozon_product(html: str, page_url: str) -> Offer | None:
    # Adapted from Grex's public widget field mapping. Only script data already
    # present in the fetched product HTML is examined; scripts are not run.
    title = None
    product_id = None
    current_price = None
    image_url = None
    gallery = []
    description = None
    rating = None
    review_count = None
    specifications: list[dict[str, str]] = []
    reviews: list[dict[str, str]] = []
    for document in embedded_json_documents(html):
        for root in _nodes(document):
            widgets = root.get("widgetStates")
            if not isinstance(widgets, dict):
                continue
            for widget_name, raw_widget in widgets.items():
                name = str(widget_name).lower()
                try:
                    widget = json.loads(raw_widget) if isinstance(raw_widget, str) else raw_widget
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(widget, dict):
                    continue
                if "webproductheading" in name:
                    title = widget.get("title") or _first_text(widget, ("title", "name")) or title
                elif "webprice" in name:
                    current_price = (
                        _ozon_widget_price(widget.get("price"))
                        or _ozon_widget_price(widget.get("currentPrice"))
                        or _ozon_price(widget)
                        or current_price
                    )
                elif "webgallery" in name:
                    product_id = widget.get("sku") or product_id
                    gallery = image_urls([gallery, widget.get("images")])
                    image_url = gallery[0] if gallery else None
                elif "webdescription" in name and not description:
                    description = _ozon_plain_text(
                        widget.get("description") or widget.get("html") or widget.get("content")
                    )
                elif "webcharacteristics" in name and not specifications:
                    specifications = _ozon_characteristics(widget)
                elif ("score" in name or "rating" in name) and "list" not in name:
                    raw_rating = _ozon_named_scalar(
                        widget, ("ratingValue", "averageRating", "rating")
                    )
                    candidate_rating = _number(raw_rating)
                    if candidate_rating is not None and candidate_rating <= 5:
                        rating = candidate_rating
                    raw_count = _ozon_named_scalar(
                        widget, ("reviewCount", "reviewsCount", "feedbackCount", "feedbacks", "ratingCount")
                    )
                    review_count = _review_total(raw_count) or review_count
                elif "review" in name and "list" in name and not reviews:
                    reviews = _ozon_review_entries(widget)
    if not title or current_price is None:
        return None
    return Offer(
        marketplace="Ozon",
        title=str(title),
        price=current_price,
        currency="RUB",
        url=page_url,
        external_id=str(product_id or _ozon_sku_from_url(page_url) or "") or None,
        image_url=image_url,
        image_urls=gallery,
        description=description,
        rating=rating,
        review_count=review_count,
        specifications=specifications,
        reviews=reviews,
    )


def extract_ozon_embedded(html: str, page_url: str, allowed_url) -> list[Offer]:
    """Read Ozon search cards from widgetStates embedded in public page scripts."""
    offers: list[Offer] = []
    seen: set[str] = set()
    for document in embedded_json_documents(html):
        for root in _nodes(document):
            widgets = root.get("widgetStates")
            if not isinstance(widgets, dict):
                continue
            for widget_name, raw_widget in widgets.items():
                widget_base_name = str(widget_name).split("-", 1)[0].lower()
                if widget_base_name not in {"tilegriddesktop", "searchresults"}:
                    continue
                try:
                    widget = json.loads(raw_widget) if isinstance(raw_widget, str) else raw_widget
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(widget, dict):
                    continue
                items = widget.get("items", [])
                if not isinstance(items, list):
                    continue
                for card in items:
                    if not isinstance(card, dict):
                        continue
                    action_link = _ozon_link(card)
                    product_url = allowed_url(action_link, page_url) if action_link else None
                    title = _ozon_title(card)
                    price = _ozon_price(card)
                    if not product_url or not title or price is None or product_url in seen:
                        continue
                    offers.append(Offer(
                        marketplace="Ozon",
                        title=title,
                        price=price,
                        currency="RUB",
                        url=product_url,
                        external_id=_ozon_sku(card) or _ozon_sku_from_url(product_url),
                        image_url=_ozon_image(card),
                    ))
                    seen.add(product_url)
    return offers
