from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Protocol
from urllib.parse import quote_plus
import re
import unicodedata


class SearchStatus(str, Enum):
    READY = "ready"
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


@dataclass(slots=True)
class ProviderResult:
    marketplace: str
    status: SearchStatus
    search_url: str
    offers: list[Offer] = field(default_factory=list)
    message: str | None = None

    def to_dict(self) -> dict:
        return {
            "marketplace": self.marketplace,
            "status": self.status.value,
            "search_url": self.search_url,
            "offers": [asdict(offer) for offer in self.offers],
            "message": self.message,
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

    def build_search_url(self, query: str) -> str:
        return self.base_search_url.format(query=quote_plus(query))

    async def search(self, query: str, limit: int = 20) -> ProviderResult:
        if not query.strip():
            raise ValueError("Search query must not be empty")
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
    if offer.gtin:
        digits = re.sub(r"\\D", "", offer.gtin)
        return f"gtin:{digits}"
    if offer.brand and offer.model:
        return f"model:{normalize_title(offer.brand)}:{normalize_title(offer.model)}"
    # Conservative fallback: only exact normalized titles are grouped.
    return f"title:{normalize_title(offer.title)}"
