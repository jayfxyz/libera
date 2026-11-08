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


# --- license denial -------------------------------------------------------

from routes.download import describe_license_denial  # noqa: E402

THROTTLED_LR = {
    "content_license": {
        "status_code": "Denied",
        "message": "License not granted to customer [X] for asin [B0001]",
        "license_denial_reasons": [
            {"message": "Customer is not part of any plans", "rejectionReason": "RequesterEligibility", "validationType": "Membership"},
            {"message": "Customer id [X] being throttled", "rejectionReason": "CustomerThrottled", "validationType": "Ownership"},
            {"message": "router does not has access", "rejectionReason": "RequesterEligibility", "validationType": "Client"},
        ],
    }
}


def test_describe_license_denial_throttled():
    msg = describe_license_denial(THROTTLED_LR)
    assert "temporarily refusing" in msg and "day or two" in msg


def test_describe_license_denial_uses_ownership_reason():
    lr = {"content_license": {"status_code": "Denied", "message": "nope", "license_denial_reasons": [
        {"message": "plans", "validationType": "Membership"},
        {"message": "Not owned", "validationType": "Ownership", "rejectionReason": "NotOwned"},
    ]}}
    assert describe_license_denial(lr) == "Audible denied the download license: Not owned"


def test_describe_license_denial_not_denied():
    assert describe_license_denial({"content_license": {"status_code": "Granted"}}) == ""
    assert describe_license_denial(None) == ""


def _item_patches(aax_result):
    """LibraryItem stand-in: the AAXC license is denied, then AAX returns aax_result."""
    class FakeItem:
        def __init__(self, data, api_client, parent, response_groups):
            self.client = api_client

        async def get_aaxc_url(self, quality):
            await self.client.post("content/B0001/licenserequest", body={})
            raise Exception("License not granted")

        async def get_aax_url_old(self, quality):
            if isinstance(aax_result, Exception):
                raise aax_result
            return aax_result

    return FakeItem


@pytest.mark.asyncio
async def test_download_info_reports_denial_on_aax_fallback():
    c = _mock_client(AsyncMock(return_value={"item": {"asin": "B0001"}}))
    c.post = AsyncMock(return_value=THROTTLED_LR)
    with (
        patch("routes.download.storage.load_client", return_value=c),
        patch("audible_cli.models.LibraryItem", _item_patches(("https://cdn/x.aax", "LC_64"))),
        patch("routes.download._get_activation_bytes", return_value="deadbeef"),
    ):
        resp = await _get("/download/acct1/B0001")

    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "aax"
    assert "temporarily refusing" in body["license_denied"]


@pytest.mark.asyncio
async def test_download_info_denial_is_the_error_when_aax_fails():
    c = _mock_client(AsyncMock(return_value={"item": {"asin": "B0001"}}))
    c.post = AsyncMock(return_value=THROTTLED_LR)
    with (
        patch("routes.download.storage.load_client", return_value=c),
        patch("audible_cli.models.LibraryItem", _item_patches(Exception("no AAX"))),
    ):
        resp = await _get("/download/acct1/B0001")

    assert resp.status_code == 502
    assert "temporarily refusing" in resp.json()["detail"]
