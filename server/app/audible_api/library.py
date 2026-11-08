"""Fetch an account's Audible library and flatten it into plain book dicts."""

from __future__ import annotations

from typing import Any

RESPONSE_GROUPS = ",".join([
    "product_desc", "product_attrs", "contributors", "series", "category_ladders",
    "media", "rating", "claim_code_url", "is_returnable", "origin_asin", "relationships",
])

_COVER_SIZES = ("2400", "1215", "500", "252")


async def fetch_library(client) -> list[dict[str, Any]]:
    async with client as c:
        resp = await c.get(
            "1.0/library",
            num_results=1000,
            response_groups=RESPONSE_GROUPS,
            sort_by="-PurchaseDate",
        )
    return [normalize_item(i) for i in resp.get("items") or []]


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    images = item.get("product_images") or {}
    cover = next((images[s] for s in _COVER_SIZES if images.get(s)), None)
    rating = ((item.get("rating") or {}).get("overall_distribution") or {}).get("average_rating")
    return {
        "asin": item.get("asin", ""),
        "title": item.get("title") or "",
        "subtitle": item.get("subtitle"),
        "description": item.get("publisher_summary"),
        "runtime_length_min": item.get("runtime_length_min") or 0,
        "authors": [a.get("name", "") for a in item.get("authors") or []],
        "narrators": [n.get("name", "") for n in item.get("narrators") or []],
        "publisher_name": item.get("publisher_name"),
        "cover_url": cover,
        "language": item.get("language"),
        "release_date": item.get("release_date"),
        "series": [
            {"asin": s.get("asin", ""), "title": s.get("title", ""), "sequence": s.get("sequence") or ""}
            for s in item.get("series") or []
        ],
        "rating": rating,
        "is_plus_catalog_item": bool(item.get("is_plus_catalog_item")),
        "date_added": (item.get("library_status") or {}).get("date_added"),
    }
