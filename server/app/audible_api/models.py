"""What the app takes from Audible's API, as typed models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

_COVER_SIZES = ("2400", "1215", "500", "252")


class Series(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asin: str = ""
    title: str = ""
    sequence: str = ""  # the book's place in the series, e.g. "3" or "1.5"


class Genre(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    name: str = ""


class AudibleBook(BaseModel):
    """A book in an account's Audible library, flattened from Audible's item."""

    model_config = ConfigDict(extra="forbid")

    asin: str
    title: str = ""
    subtitle: str | None = None
    description: str | None = None
    runtime_length_min: int = 0
    authors: list[str] = []
    narrators: list[str] = []
    publisher_name: str | None = None
    cover_url: str | None = None  # the largest Audible offers
    language: str | None = None
    release_date: str | None = None
    series: list[Series] = []
    rating: float | None = None
    genres: list[list[Genre]] = []  # Audible's category ladders, top-level first
    is_plus_catalog_item: bool = False
    is_downloadable: bool = True  # customer_rights.is_consumable_offline; False for locked Plus/Music borrows
    date_added: str | None = None
    has_pdf: bool | None = None  # a companion PDF exists; None: the scan didn't say

    @classmethod
    def from_audible(cls, item: dict[str, Any]) -> AudibleBook:
        """From one item of Audible's 1.0/library response."""
        images = item.get("product_images") or {}
        rights = item.get("customer_rights")
        is_downloadable = bool(rights.get("is_consumable_offline", True)) if isinstance(rights, dict) else True
        return cls(
            asin=item.get("asin", ""),
            title=item.get("title") or "",
            subtitle=item.get("subtitle"),
            description=item.get("publisher_summary"),
            runtime_length_min=item.get("runtime_length_min") or 0,
            authors=[a.get("name", "") for a in item.get("authors") or []],
            narrators=[n.get("name", "") for n in item.get("narrators") or []],
            publisher_name=item.get("publisher_name"),
            cover_url=next((images[s] for s in _COVER_SIZES if images.get(s)), None),
            language=item.get("language"),
            release_date=item.get("release_date"),
            series=[Series(asin=s.get("asin", ""), title=s.get("title", ""), sequence=s.get("sequence") or "")
                    for s in item.get("series") or []],
            rating=((item.get("rating") or {}).get("overall_distribution") or {}).get("average_rating"),
            genres=[[Genre(id=str(r.get("id") or ""), name=r.get("name") or "") for r in ladder.get("ladder") or []]
                    for ladder in item.get("category_ladders") or []],
            is_plus_catalog_item=bool(item.get("is_plus_catalog_item")),
            is_downloadable=is_downloadable,
            date_added=(item.get("library_status") or {}).get("date_added"),
            has_pdf=bool(item.get("pdf_url")),  # only the flag: the URL is fetched fresh when needed
        )
