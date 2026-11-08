"""
Unit tests for the download routes. storage and audible client are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

CHAPTER_INFO = {
    "brandIntroDurationMs": 1532,
    "brandOutroDurationMs": 3204,
    "is_accurate": True,
    "runtime_length_ms": 20000,
    "chapters": [
        {"title": "Opening Credits", "start_offset_ms": 0, "length_ms": 5000},
        {
            "title": "Part 1",
            "start_offset_ms": 5000,
            "length_ms": 2000,
            "chapters": [
                {"title": "Chapter 1", "start_offset_ms": 7000, "length_ms": 13000},
            ],
        },
    ],
}


def _mock_client(get):
    c = MagicMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    c.get = get
    return c


async def _get(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.get(path)


@pytest.mark.asyncio
async def test_get_chapters_returns_chapter_info():
    get = AsyncMock(return_value={"content_metadata": {"chapter_info": CHAPTER_INFO}})
    with patch("routes.download.storage.load_client", return_value=_mock_client(get)):
        resp = await _get("/download/acct1/B0001/chapters")

    assert resp.status_code == 200
    assert resp.json() == CHAPTER_INFO
    path = get.call_args.args[0]
    params = get.call_args.kwargs["params"]
    assert path == "content/B0001/metadata"
    assert params["chapter_titles_type"] == "Tree"
    assert "chapter_info" in params["response_groups"]


@pytest.mark.asyncio
async def test_get_chapters_404_when_no_chapters():
    get = AsyncMock(return_value={"content_metadata": {}})
    with patch("routes.download.storage.load_client", return_value=_mock_client(get)):
        resp = await _get("/download/acct1/B0001/chapters")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_chapters_unknown_account():
    with patch("routes.download.storage.load_client", side_effect=FileNotFoundError):
        resp = await _get("/download/nope/B0001/chapters")
    assert resp.status_code == 404
