from fastapi import APIRouter, HTTPException
import storage

router = APIRouter()


@router.get("/{account_id}")
async def get_library(account_id: str):
    """
    Fetch all library items for the given account from Audible.
    Returns a list of book DTOs that the Go backend will import into its DB.
    """
    try:
        client = storage.load_client(account_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_id}")

    response_groups = [
        "product_desc",
        "product_attrs",
        "contributors",
        "series",
        "category_ladders",
        "media",
        "rating",
        "claim_code_url",
        "is_returnable",
        "origin_asin",
        "relationships",
    ]

    try:
        async with client as c:
            library = await c.get(
                "1.0/library",
                num_results=1000,
                response_groups=",".join(response_groups),
                sort_by="-PurchaseDate",
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Audible library fetch failed: {e}")

    items = library.get("items", [])
    return _normalize_items(items)


def _normalize_items(items: list) -> list:
    """Flatten the Audible API response into a stable shape for Go to consume."""
    result = []
    for item in items:
        authors = [a.get("name", "") for a in item.get("authors") or []]
        narrators = [n.get("name", "") for n in item.get("narrators") or []]
        series = [
            {
                "asin": s.get("asin", ""),
                "title": s.get("title", ""),
                "sequence": s.get("sequence", ""),
            }
            for s in item.get("series") or []
        ]
        categories = [
            rung.get("name", "")
            for entry in item.get("category_ladders") or []
            for rung in [((entry.get("ladder") or entry) or [{}])[-1]]
            if rung
        ]
        cover = None
        for res in ["2400", "1215", "500", "252"]:
            key = f"product_images.{res}"
            if item.get(key):
                cover = item[key]
                break
        if not cover:
            cover = item.get("product_images", {}).get("500")

        result.append({
            "asin": item.get("asin", ""),
            "title": item.get("title", ""),
            "subtitle": item.get("subtitle"),
            "description": item.get("publisher_summary"),
            "runtime_length_min": item.get("runtime_length_min", 0),
            "authors": authors,
            "narrators": narrators,
            "publisher_name": item.get("publisher_name"),
            "cover_url": cover,
            "language": item.get("language"),
            "release_date": item.get("release_date"),
            "series": series,
            "categories": categories,
            "rating": item.get("rating", {}).get("overall_distribution", {}).get("average_rating"),
            "is_plus_catalog_item": item.get("is_plus_catalog_item", False),
            "date_added": item.get("library_status", {}).get("date_added"),
        })

    return result
