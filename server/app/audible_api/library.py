"""Fetch an account's Audible library as AudibleBook models."""

from __future__ import annotations

from .models import AudibleBook

RESPONSE_GROUPS = ",".join([
    "product_desc", "product_attrs", "contributors", "series", "category_ladders",
    "media", "rating", "claim_code_url", "is_returnable", "origin_asin", "relationships", "pdf_url",
    "customer_rights",
])


async def fetch_library(client) -> list[AudibleBook]:
    async with client as c:
        resp = await c.get(
            "1.0/library",
            num_results=1000,
            response_groups=RESPONSE_GROUPS,
            sort_by="-PurchaseDate",
        )
    return [AudibleBook.from_audible(i) for i in resp.get("items") or []]
