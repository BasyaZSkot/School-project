from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Protocol
from urllib.parse import quote_plus
import math
import re
import unicodedata


MAX_PROVIDER_LIMIT = 200


class SearchStatus(str, Enum):
    READY = "ready"
    NO_RESULTS = "no_results"
    DISABLED = "disabled"
    ACCESS_REQUIRED = "access_required"
    POLICY_RESTRICTED = "policy_restricted"
    ERROR = "error"


@dataclass(slots=True)
class Offer:
    marketplace: str
    title: str
    price: float
    currency: str
    url: str
    external_id: str | None = None
    brand: str | None = None
    model: str | None = None
    gtin: str | None = None
    in_stock: bool | None = None
    image_url: str | None = None
    description: str | None = None
    rating: float | None = None
    review_count: int | None = None
    specifications: list[dict[str, str]] = field(default_factory=list)
    reviews: list[dict[str, str]] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    delivery: dict = field(default_factory=dict)
    seller: str | None = None
    condition: str | None = None
    variants: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = self.title.strip()
        self.currency = self.currency.upper().strip()
        if not self.title:
            raise ValueError("Offer title must not be empty")
        if not math.isfinite(self.price) or self.price <= 0:
            raise ValueError("Offer price must be a finite positive number")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Offer currency must be a three-letter code")
        if not self.url.startswith("https://"):
            raise ValueError("Offer URL must use HTTPS")
        from .variants import extract
        self.variants = extract(self.title, self.specifications, self.variants, self.brand, self.model, self.condition)


@dataclass(slots=True)
class ProviderResult:
    marketplace: str
    status: SearchStatus
    search_url: str
    offers: list[Offer] = field(default_factory=list)
    message: str | None = None
    has_more: bool | None = None

    def to_dict(self) -> dict:
        return {
            "marketplace": self.marketplace,
            "status": self.status.value,
            "search_url": self.search_url,
            "offers": [asdict(offer) for offer in self.offers],
            "message": self.message,
            "has_more": self.has_more,
        }


class SearchAdapter(Protocol):
    marketplace: str

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        ...


class DisabledAdapter:
    """A deliberately non-scraping adapter until an approved data source exists."""

    marketplace: str
    reason: str
    status: SearchStatus = SearchStatus.ACCESS_REQUIRED
    base_search_url: str

    def __init__(
        self,
        marketplace: str,
        reason: str,
        base_search_url: str,
        status: SearchStatus = SearchStatus.ACCESS_REQUIRED,
    ):
        self.marketplace = marketplace
        self.reason = reason
        self.base_search_url = base_search_url
        self.status = status

    def build_search_url(self, query: str) -> str:
        return self.base_search_url.format(query=quote_plus(query))

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= MAX_PROVIDER_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_PROVIDER_LIMIT}")
        return ProviderResult(
            marketplace=self.marketplace,
            status=self.status,
            search_url=self.build_search_url(query),
            message=self.reason,
        )


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^0-9a-zа-яё]+", " ", value)
    return " ".join(value.split())


def offer_group_key(offer: Offer) -> str:
    from .variants import signature
    suffix = ":variant:" + signature(offer)
    if offer.gtin:
        digits = "".join(char for char in offer.gtin if char.isdigit())
        if len(digits) in {8, 12, 13, 14}:
            return f"gtin:{digits}" + suffix
    if offer.brand and offer.model:
        return f"model:{normalize_title(offer.brand)}:{normalize_title(offer.model)}" + suffix
    return f"title:{normalize_title(offer.title)}" + suffix
