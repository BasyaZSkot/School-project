"""Extract marketplace-specific product state already embedded in public HTML.

No network requests are made here. In particular, this module does not call
private marketplace endpoints, obtain browser cookies, or automate challenges.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .base import Offer
from .wb_adapter import wb_record_to_offer


class _StateScriptParser(HTMLParser):
    """Collect JSON script payloads included in the HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture = False
        self._parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "script":
            return
        values = dict(attrs)
        script_type = (values.get("type") or "").lower()
        script_id = (values.get("id") or "").lower()
        self._capture = (
            "json" in script_type
            or script_id in {"__next_data__", "__initial_state__", "initial-state", "app-state"}
        )
        if self._capture:
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


def embedded_json_documents(html: str) -> list[Any]:
    """Return parseable JSON documents found in explicit JSON script tags."""
    parser = _StateScriptParser()
    parser.feed(html)
    parser.close()
    documents: list[Any] = []
    for raw in parser.documents:
        try:
            documents.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
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
    """Read WB products only from a JSON payload embedded in the public page."""
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
    # Ozon marks the active price explicitly; do not accidentally use
    # ORIGINAL_PRICE when the discounted PRICE is also present.
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


def extract_ozon_embedded(html: str, page_url: str, allowed_url) -> list[Offer]:
    """Read tileGridDesktop search cards from widgetStates embedded in public HTML."""
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
