import json
import os
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlparse, urlunparse

from .base import MAX_PROVIDER_LIMIT, Offer, ProviderResult, SearchStatus
from .feed import JsonFeedAdapter
from .public_html import PublicHtmlSearchAdapter, _price_from_offer
from .product_data import MAX_SPECIFICATIONS, delivery_data, image_urls
from .yandex_delivery import extract_yandex_deliveries


MAX_SEARCH_PAGES = 50


def _merge_specifications(*groups):
    merged = []
    seen = set()
    for group in groups:
        for item in group or []:
            if not isinstance(item, dict):
                continue
            name = " ".join(str(item.get("name") or "").split())
            value = " ".join(str(item.get("value") or "").split())
            if not name or not value:
                continue
            identity = name.casefold()
            if identity in seen:
                continue
            merged.append({"name": name[:120], "value": value[:500]})
            seen.add(identity)
            if len(merged) >= MAX_SPECIFICATIONS:
                return merged
    return merged


def _find_named_specification_value(value, name, depth=0):
    if depth > 12:
        return None
    if isinstance(value, dict):
        candidate_name = " ".join(str(value.get("name") or "").split())
        if candidate_name.casefold() == name.casefold():
            candidate = value.get("value") or value.get("valueReference")
            if isinstance(candidate, (str, int, float)) and str(candidate).strip():
                return str(candidate).strip()
            if isinstance(candidate, list):
                values = [str(item).strip() for item in candidate if item is not None]
                return ", ".join(item for item in values if item) or None
        for child in value.values():
            found = _find_named_specification_value(child, name, depth + 1)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_named_specification_value(child, name, depth + 1)
            if found:
                return found
    return None


def _is_yandex_widget_state(value, depth=0):
    if depth > 12:
        return False
    if isinstance(value, dict):
        if any(
            "widgets" in str(key).casefold()
            or "copyablespecitem" in str(key).casefold()
            for key in value
        ):
            return True
        return any(_is_yandex_widget_state(child, depth + 1) for child in value.values())
    if isinstance(value, list):
        return any(_is_yandex_widget_state(child, depth + 1) for child in value)
    return False


def _clean_yandex_specification_value(name, raw_value):
    value = " ".join(str(raw_value or "").split())
    if not value:
        return None
    if value.startswith(("{", "[")):
        try:
            payload, _ = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            extracted = _find_named_specification_value(payload, name)
            if extracted:
                return " ".join(extracted.split())
            if _is_yandex_widget_state(payload):
                return None
    return value


class _YandexProductStateParser(HTMLParser):
    # Read public data-auto fields used by Grex's Yandex product parser.
    _targets = {
        "productCardTitle",
        "snippet-price-old",
        "snippet-price-current",
        "product-spec",
    }
    _void_tags = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._tags = []
        self._captures = []
        self.values = {}
        self.specifications = []
        self._spec_row = None
        self.images = []
        self._gallery_depth = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        depth = len(self._tags) + 1
        target = attrs.get("data-auto")
        zone = (attrs.get("data-zone-name", "") + " " + str(target or "")).casefold()
        if any(name in zone for name in ("productgallery", "product-gallery", "product-picture", "product-image", "media-viewer")):
            self._gallery_depth = depth
        if tag == "meta" and attrs.get("property") == "og:image":
            self.images.append(attrs.get("content"))
        if tag == "img" and (self._gallery_depth is not None or attrs.get("itemprop") == "image"):
            self.images.append(attrs.get("src") or attrs.get("data-src"))
        if target in {"delivery", "delivery-text", "snippet-delivery", "delivery-estimate"}:
            self._captures.append({"tag": tag, "depth": depth, "target": "delivery", "parts": []})

        # In the public product markup the value is the second direct child of
        # the row three levels above span[data-auto="product-spec"].
        if (
            self._spec_row is not None
            and self._spec_row["phase"] == "waiting_value"
            and len(self._tags) == self._spec_row["row_depth"]
        ):
            self._spec_row["phase"] = "value"
            self._spec_row["value_tag"] = tag
            self._spec_row["value_depth"] = depth
            self._spec_row["value_parts"] = []

        if target in self._targets:
            capture = {
                "tag": tag,
                "depth": depth,
                "target": target,
                "parts": [],
            }
            self._captures.append(capture)
            if target == "product-spec" and len(self._tags) >= 3:
                row_depth = len(self._tags) - 2
                self._spec_row = {
                    "row_depth": row_depth,
                    "row_tag": self._tags[row_depth - 1],
                    "label_child_tag": self._tags[row_depth],
                    "phase": "label",
                    "name": None,
                }

        if tag not in self._void_tags:
            self._tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._void_tags:
            self.handle_starttag(tag, attrs)
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        for capture in self._captures:
            capture["parts"].append(data)
        if self._spec_row is not None and self._spec_row["phase"] == "value":
            self._spec_row["value_parts"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        close_index = next(
            (index for index in range(len(self._tags) - 1, -1, -1)
             if self._tags[index] == tag),
            None,
        )
        if close_index is None:
            return
        depth = close_index + 1
        if self._gallery_depth is not None and depth <= self._gallery_depth:
            self._gallery_depth = None
        remaining = []
        for capture in self._captures:
            if capture["tag"] == tag and capture["depth"] == depth:
                value = " ".join(" ".join(capture["parts"]).split())
                if value:
                    if capture["target"] == "product-spec" and self._spec_row is not None:
                        self._spec_row["name"] = value
                    else:
                        self.values.setdefault(capture["target"], []).append(value)
            else:
                remaining.append(capture)
        self._captures = remaining

        row = self._spec_row
        if row is not None:
            if (
                row["phase"] == "label"
                and depth == row["row_depth"] + 1
                and tag == row["label_child_tag"]
            ):
                row["phase"] = "waiting_value"
            elif (
                row["phase"] == "value"
                and depth == row["value_depth"]
                and tag == row["value_tag"]
            ):
                self._append_specification(
                    row.get("name"), " ".join(" ".join(row["value_parts"]).split())
                )
                self._spec_row = None
            elif depth == row["row_depth"] and tag == row["row_tag"]:
                self._spec_row = None

        del self._tags[close_index:]

    def _append_specification(self, name, value):
        name = " ".join(str(name or "").split())
        value = _clean_yandex_specification_value(name, value)
        if not name or not value:
            return
        if len(name) > 120 or len(value) > 500:
            return
        identity = name.casefold()
        if any(
            item["name"].casefold() == identity
            for item in self.specifications
        ):
            return
        if len(self.specifications) < MAX_SPECIFICATIONS:
            self.specifications.append({"name": name, "value": value})


class _YandexSearchCardsParser(HTMLParser):
    """Read titles, prices, links and images from public search-card markup."""

    _text_targets = {
        "snippet-title": "title",
        "snippet-price-current": "price",
        "snippet-delivery": "delivery",
        "delivery-estimate": "delivery",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._tags = []
        self._captures = []
        self._card = None
        self.cards = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        depth = len(self._tags) + 1
        target = attrs.get("data-auto")

        if target == "searchOrganic":
            self._finish_card()
            self._card = {
                "tag": tag,
                "depth": depth,
                "title": [],
                "price": [],
                "url": None,
                "image_url": None,
                "delivery": [],
            }
        elif self._card is not None:
            field = self._text_targets.get(target)
            if field:
                self._captures.append({
                    "tag": tag,
                    "depth": depth,
                    "field": field,
                    "parts": [],
                })

            href = attrs.get("href", "")
            if (
                self._card["url"] is None
                and tag == "a"
                and ("/card/" in href or "/product/" in href)
            ):
                self._card["url"] = href

            if self._card["image_url"] is None and tag == "img":
                image = attrs.get("src") or attrs.get("data-src")
                if not image and attrs.get("srcset"):
                    image = attrs["srcset"].split(",", 1)[0].strip().split(" ", 1)[0]
                self._card["image_url"] = image

        self._tags.append(tag)

    def handle_data(self, data):
        for capture in self._captures:
            capture["parts"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        close_index = next(
            (index for index in range(len(self._tags) - 1, -1, -1)
             if self._tags[index] == tag),
            None,
        )
        if close_index is None:
            return

        depth = close_index + 1
        remaining = []
        for capture in self._captures:
            if capture["tag"] == tag and capture["depth"] == depth:
                value = " ".join(" ".join(capture["parts"]).split())
                if value and self._card is not None:
                    self._card[capture["field"]].append(value)
            else:
                remaining.append(capture)
        self._captures = remaining

        if (
            self._card is not None
            and self._card["tag"] == tag
            and self._card["depth"] == depth
        ):
            self._finish_card()
        del self._tags[close_index:]

    def close(self):
        super().close()
        self._finish_card()

    def _finish_card(self):
        if self._card is None:
            return
        card = self._card
        self._card = None
        self._captures = []
        self.cards.append(card)


class YandexMarketAdapter(PublicHtmlSearchAdapter):
    """Yandex Market public-page connector."""

    marketplace = "Яндекс Маркет"
    base_search_url = "https://market.yandex.ru/search?text={query}"
    allowed_hosts = ("market.yandex.ru",)

    def _extract(self, html: str, page_url: str, limit: int):
        parser = _YandexSearchCardsParser()
        parser.feed(html)
        parser.close()
        deliveries, _ = extract_yandex_deliveries(html)

        offers = []
        seen = set()
        for card in parser.cards:
            titles = card["title"]
            prices = card["price"]
            title = titles[0] if titles else None
            raw_url = card["url"]
            product_url = self._valid_marketplace_url(raw_url, page_url) if raw_url else None
            price = next(
                (_price_from_offer({"price": raw_price}) for raw_price in prices
                 if _price_from_offer({"price": raw_price}) is not None),
                None,
            )
            if not title or price is None or not product_url:
                continue

            parsed_url = urlparse(product_url)
            product_url = urlunparse(parsed_url._replace(query="", fragment=""))
            if product_url in seen:
                continue
            seen.add(product_url)

            raw_image = card["image_url"]
            image_url = urljoin(page_url, raw_image) if raw_image else None
            if image_url and urlparse(image_url).scheme != "https":
                image_url = None
            path_parts = [part for part in parsed_url.path.split("/") if part]
            product_id = next(
                (part for part in reversed(path_parts) if part.isdigit()),
                path_parts[-1] if path_parts else None,
            )
            offers.append(Offer(
                marketplace=self.marketplace,
                title=title,
                price=price,
                currency="RUB",
                url=product_url,
                external_id=product_id,
                image_url=image_url,
                image_urls=image_urls(image_url),
                delivery=deliveries.get(parsed_url.path.rstrip("/")) or (delivery_data(card["delivery"][0]) if card["delivery"] else {}),
            ))
            if len(offers) >= limit:
                break

        structured = super()._extract(html, page_url, limit)
        if not offers:
            return structured
        by_path = {urlparse(item.url).path.rstrip("/"): item for item in structured}
        for offer in offers:
            extra = by_path.get(urlparse(offer.url).path.rstrip("/"))
            if extra is not None:
                for name in ("brand", "model", "rating", "review_count", "specifications", "reviews", "delivery", "image_urls"):
                    value = getattr(extra, name)
                    if value is not None and value != [] and value != {}:
                        setattr(offer, name, {**value, **offer.delivery} if name == "delivery" else value)
        return offers

    @staticmethod
    def _is_challenge_page(page_url: str, html: str) -> bool:
        if urlparse(page_url).path.rstrip("/").lower() == "/showcaptcha":
            return True
        prefix = html[:30000].lower()
        return "smartcaptcha" in prefix or "checkbox-captcha" in prefix

    async def search(self, query: str, limit: int = 20):
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= MAX_PROVIDER_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_PROVIDER_LIMIT}")

        clean_query = " ".join(query.split())
        search_url = self.search_url.format(query=quote_plus(clean_query))
        final_url, html = await self._fetch_public_page(search_url)
        if self._is_challenge_page(final_url, html):
            return ProviderResult(
                marketplace=self.marketplace,
                status=SearchStatus.POLICY_RESTRICTED,
                search_url=search_url,
                offers=[],
                message="Яндекс Маркет вернул страницу проверки вместо результатов поиска.",
            )

        offers = self._extract(html, final_url, limit)
        result = ProviderResult(
            marketplace=self.marketplace,
            status=SearchStatus.READY if offers else SearchStatus.NO_RESULTS,
            search_url=search_url,
            offers=offers,
            message=None if offers else "Страница доступна, но карточки не найдены в поддерживаемой разметке.",
        )
        if result.status != SearchStatus.READY or len(result.offers) >= limit:
            return result

        offers = list(result.offers)
        seen = {offer.external_id or offer.url for offer in offers}
        base = urlparse(search_url)
        for page in range(2, MAX_SEARCH_PAGES + 1):
            query_items = [
                (key, value) for key, value in parse_qsl(base.query, keep_blank_values=True)
                if key != "page"
            ]
            query_items.append(("page", str(page)))
            page_url = urlunparse(base._replace(query=urlencode(query_items)))
            try:
                final_url, html = await self._fetch_public_page(page_url)
            except Exception:
                result.message = "Дополнительные страницы недоступны; показаны уже найденные товары."
                result.has_more = True
                break
            if self._is_challenge_page(final_url, html):
                result.message = "Для дополнительных страниц Яндекс Маркет запросил проверку; показаны найденные товары."
                result.has_more = True
                break

            remaining = limit - len(offers)
            page_offers = self._extract(html, final_url, remaining)
            added = [
                offer for offer in page_offers
                if (offer.external_id or offer.url) not in seen
            ]
            if not added:
                result.has_more = False
                break
            for offer in added:
                identity = offer.external_id or offer.url
                seen.add(identity)
                offers.append(offer)
                if len(offers) >= limit:
                    break
            if len(offers) >= limit:
                break
        else:
            if len(offers) < limit:
                result.has_more = False
                result.message = (
                    f"Достигнут предел в {MAX_SEARCH_PAGES} публичных страниц; "
                    "показаны найденные товары."
                )

        result.offers = offers[:limit]
        if len(result.offers) < limit and result.message is None:
            result.message = "Показаны карточки с доступных публичных страниц поиска."
        return result

    def _extract_product(self, html: str, page_url: str):
        parser = _YandexProductStateParser()
        parser.feed(html)
        parser.close()
        _, primary_delivery = extract_yandex_deliveries(html)
        titles = parser.values.get("productCardTitle", [])
        current_prices = parser.values.get("snippet-price-current", [])
        title = titles[0] if titles else None
        price = None
        for raw_price in current_prices:
            price = _price_from_offer({"price": raw_price})
            if price is not None:
                break
        structured = super()._extract_product(html, page_url)
        if structured is not None:
            structured.specifications = _merge_specifications(
                parser.specifications, structured.specifications
            )
            structured.image_urls = image_urls([structured.image_urls, parser.images], page_url)
            structured.image_url = structured.image_url or next(iter(structured.image_urls), None)
            if not structured.delivery and parser.values.get("delivery"):
                structured.delivery = delivery_data(parser.values["delivery"][0])
            structured.delivery = {**structured.delivery, **primary_delivery}
        if not title or price is None:
            return structured
        product_id = re.search(r"/card/([^/]+)", urlparse(page_url).path)
        offer = Offer(
            marketplace=self.marketplace,
            title=title,
            price=price,
            currency="RUB",
            url=page_url,
            external_id=product_id.group(1) if product_id else None,
        )
        if structured is not None:
            offer.description = structured.description
            offer.rating = structured.rating
            offer.review_count = structured.review_count
            offer.specifications = structured.specifications
            offer.reviews = structured.reviews
            offer.image_url = structured.image_url
            offer.image_urls = structured.image_urls
            offer.delivery = structured.delivery
        else:
            offer.specifications = parser.specifications
            offer.image_urls = image_urls(parser.images, page_url)
            offer.image_url = next(iter(offer.image_urls), None)
            offer.delivery = primary_delivery or delivery_data(parser.values.get("delivery", [None])[0])
        return offer

    @classmethod
    def from_env(cls):
        feed_url = os.getenv("MULTIMARKET_YM_FEED_URL", "").strip()
        if feed_url:
            return JsonFeedAdapter(
                marketplace=cls.marketplace,
                base_search_url=cls.base_search_url,
                reason="Подключён разрешённый партнёрский источник Яндекс Маркета.",
                feed_url=feed_url,
                token=os.getenv("MULTIMARKET_YM_FEED_TOKEN", "").strip() or None,
                allowed_hosts=cls.allowed_hosts,
            )
        return cls(
            marketplace=cls.marketplace,
            search_url=cls.base_search_url,
            allowed_hosts=cls.allowed_hosts,
        )
