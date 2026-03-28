"""
Unit tests for library route. storage and audible client are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


MOCK_ITEMS = [
    {
        "asin": "B001234567",
        "title": "Test Book",
        "subtitle": None,
        "publisher_summary": "A great book.",
        "runtime_length_min": 600,
        "authors": [{"name": "Jane Author"}],
        "narrators": [{"name": "Joe Narrator"}],
        "publisher_name": "Audible Originals",
        "product_images": {"500": "https://cdn.example.com/cover.jpg"},
        "language": "english",
        "release_date": "2023-01-15",
        "series": [{"asin": "S001", "title": "Test Series", "sequence": "1"}],
        "category_ladders": [[{"name": "Fiction"}]],
        "rating": {"overall_distribution": {"average_rating": 4.5}},
        "is_plus_catalog_item": False,
        "library_status": {"date_added": "2023-02-01"},
    }
]


@pytest.mark.asyncio
async def test_get_library_normalizes_items():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value={"items": MOCK_ITEMS})

    with (
        patch("routes.library.storage.load_client", return_value=mock_client),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/library/test_account")

    assert resp.status_code == 200
    books = resp.json()
    assert len(books) == 1
    book = books[0]
    assert book["asin"] == "B001234567"
    assert book["title"] == "Test Book"
    assert book["authors"] == ["Jane Author"]
    assert book["narrators"] == ["Joe Narrator"]
    assert book["series"][0]["title"] == "Test Series"
    assert book["categories"] == ["Fiction"]
    assert book["rating"] == 4.5


@pytest.mark.asyncio
async def test_get_library_account_not_found():
    with patch("routes.library.storage.load_client", side_effect=FileNotFoundError("no tokens")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/library/unknown_account")

    assert resp.status_code == 404
