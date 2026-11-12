"""Delivery data published in Yandex Market's public HTML, without follow-up APIs."""
from __future__ import annotations

from html.parser import HTMLParser
import json
from urllib.parse import urlparse

from .product_data import delivery_data

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def _zone_data(attrs):
    try:
        value = json.loads(attrs.get("data-zone-data", "{}"))
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _normalize(options, destination, reference_date=None, region_id=None):
    normalized = []
    for option in options:
        data = option["data"]
        currency = data.get("priceCurrency")
        text = data.get("deliveryText") or " ".join(option["parts"])
        raw = {
            "text": text.replace("*", " ") if isinstance(text, str) else "",
            "earliest_date": data.get("deliveryDateFrom"),
            "latest_date": data.get("deliveryDateTo"),
            "cost": data.get("priceValue"),
            "currency": "RUB" if currency == "RUR" else currency,
            "destination": destination,
            "method": {"PICKUP": "Пункт выдачи", "ON_DEMAND": "По клику"}.get(data.get("deliveryType")),
        }
        delivery = delivery_data(raw, reference_date=reference_date)
        if region_id is not None:
            delivery["region_id"] = region_id
        if delivery:
            normalized.append((data.get("selected") is True, delivery))
    # A selected delivery method takes precedence. Do not combine one method's
    # earliest date with another method's cost or latest date.
    selected = next((d for chosen, d in normalized if chosen), None)
    return selected or next((d for _, d in normalized if d.get("latest_date") or d.get("max_days") is not None),
                            normalized[0][1] if normalized else {})


class _DeliveryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.captures = []
        self.card = None
        self.cards = []
        self.primary_depth = None
        self.primary = []
        self.destination = ""
        self.region_id = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        depth = len(self.tags) + 1
        auto, zone = attrs.get("data-auto"), attrs.get("data-zone-name")
        if auto == "searchOrganic":
            self.card = {"depth": depth, "path": None, "options": []}
            self.cards.append(self.card)
        if auto == "snippet-delivery-options" and self.card is None:
            self.primary_depth = depth
        if zone == "deliveryPoint":
            region = _zone_data(attrs).get("regionId")
            if isinstance(region, int) and not isinstance(region, bool):
                self.region_id = region
            self.captures.append({"depth": depth, "parts": [], "destination": True})
        option = None
        if self.card is not None:
            href = attrs.get("href", "")
            if tag == "a" and not self.card["path"] and ("/card/" in href or "/product/" in href):
                self.card["path"] = urlparse(href).path.rstrip("/")
            if auto == "delivery-wrapper" or zone == "deliveryInfo":
                option = {"depth": depth, "data": _zone_data(attrs), "parts": []}
                self.card["options"].append(option)
        elif self.primary_depth is not None and zone == "deliveryVariant":
            option = {"depth": depth, "data": _zone_data(attrs), "parts": []}
            self.primary.append(option)
        if option is not None:
            self.captures.append(option)
        if tag not in _VOID:
            self.tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if "script" in self.tags or "style" in self.tags:
            return
        if data.strip():
            for capture in self.captures:
                capture["parts"].append(data.strip())

    def handle_endtag(self, tag):
        close = next((i for i in range(len(self.tags) - 1, -1, -1) if self.tags[i] == tag.lower()), None)
        if close is None:
            return
        depth = close + 1
        for capture in self.captures[:]:
            if capture["depth"] >= depth:
                self.captures.remove(capture)
                if capture.get("destination"):
                    self.destination = " ".join(capture["parts"]).removesuffix("Укажите адрес").strip(" •·,")[:120]
        if self.card is not None and self.card["depth"] >= depth:
            self.card = None
        if self.primary_depth is not None and self.primary_depth >= depth:
            self.primary_depth = None
        del self.tags[close:]


def extract_yandex_deliveries(html, *, reference_date=None):
    parser = _DeliveryParser()
    parser.feed(html)
    parser.close()
    by_path = {card["path"]: _normalize(card["options"], parser.destination, reference_date, parser.region_id)
               for card in parser.cards if card["path"]}
    return by_path, _normalize(parser.primary, parser.destination, reference_date, parser.region_id)
