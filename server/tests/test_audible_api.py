from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.audible_api import content
from app.audible_api.auth import LoginError, LoginFlow
from app.audible_api.content import ContentError, describe_license_denial
from app.audible_api.library import normalize_item


def fake_client(get=None, post=None):
    c = MagicMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    c.get = get or AsyncMock(return_value={})
    c.post = post or AsyncMock(return_value={})
    return c


THROTTLED = {"content_license": {
    "status_code": "Denied",
    "message": "License not granted to customer [X] for asin [B0001]",
    "license_denial_reasons": [
        {"message": "Customer is not part of any plans", "rejectionReason": "RequesterEligibility",
         "validationType": "Membership"},
        {"message": "Customer id [X] being throttled", "rejectionReason": "CustomerThrottled",
         "validationType": "Ownership"},
    ],
}}


# --- license denial -----------------------------------------------------------

def test_describe_license_denial():
    assert "temporarily refusing" in describe_license_denial(THROTTLED)
    owned = {"content_license": {"status_code": "Denied", "message": "nope", "license_denial_reasons": [
        {"message": "plans", "validationType": "Membership"},
        {"message": "Not owned", "validationType": "Ownership", "rejectionReason": "NotOwned"}]}}
    assert describe_license_denial(owned) == "Audible denied the download license: Not owned"
    assert describe_license_denial({"content_license": {"status_code": "Granted"}}) == ""
    assert describe_license_denial(None) == ""


def fake_item(aax_result):
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


async def test_aax_fallback_reports_license_denial():
    c = fake_client(get=AsyncMock(return_value={"item": {"asin": "B0001"}}), post=AsyncMock(return_value=THROTTLED))
    c.auth.get_activation_bytes.return_value = "deadbeef"
    with patch("audible_cli.models.LibraryItem", fake_item(("https://cdn/x.aax", "LC_64"))):
        info = await content.get_download_info(c, "B0001")
    assert (info.format, info.download_url, info.activation_bytes) == ("aax", "https://cdn/x.aax", "deadbeef")
    assert "temporarily refusing" in info.license_denied


async def test_denial_is_the_error_when_aax_also_fails():
    c = fake_client(get=AsyncMock(return_value={"item": {}}), post=AsyncMock(return_value=THROTTLED))
    with patch("audible_cli.models.LibraryItem", fake_item(Exception("no AAX"))):
        with pytest.raises(ContentError, match="temporarily refusing"):
            await content.get_download_info(c, "B0001")


async def test_aaxc_success_returns_key_and_iv():
    class Item:
        def __init__(self, **kw):
            pass

        async def get_aaxc_url(self, quality):
            return "https://cdn/x.aaxc", "AAX_44_128", {"content_license": {"license_response": {"key": "k", "iv": "i"}}}

    c = fake_client(get=AsyncMock(return_value={"item": {}}))
    with patch("audible_cli.models.LibraryItem", Item):
        info = await content.get_download_info(c, "B0001")
    assert (info.format, info.key, info.iv, info.license_denied) == ("aaxc", "k", "i", "")


# --- chapters -------------------------------------------------------------------

async def test_chapter_info_requests_tree():
    info = {"runtime_length_ms": 20000, "chapters": [{"title": "Chapter 1", "start_offset_ms": 0, "length_ms": 20000}]}
    get = AsyncMock(return_value={"content_metadata": {"chapter_info": info}})
    assert await content.get_chapter_info(fake_client(get=get), "B0001") == info
    assert get.call_args.args[0] == "content/B0001/metadata"
    params = get.call_args.kwargs["params"]
    assert params["chapter_titles_type"] == "Tree" and "chapter_info" in params["response_groups"]


async def test_chapter_info_missing():
    with pytest.raises(ContentError):
        await content.get_chapter_info(fake_client(get=AsyncMock(return_value={"content_metadata": {}})), "B0001")


# --- library ---------------------------------------------------------------------

def test_normalize_item():
    got = normalize_item({
        "asin": "B001", "title": "Test Book", "publisher_summary": "A great book.", "runtime_length_min": 600,
        "authors": [{"name": "Jane Author"}], "narrators": [{"name": "Joe Narrator"}],
        "publisher_name": "Audible Originals",
        "product_images": {"500": "https://cdn/500.jpg", "1215": "https://cdn/1215.jpg"},
        "language": "english", "release_date": "2023-01-15",
        "series": [{"asin": "S001", "title": "Test Series", "sequence": "1"}],
        "rating": {"overall_distribution": {"average_rating": 4.5}},
        "is_plus_catalog_item": False, "library_status": {"date_added": "2023-02-01"},
    })
    assert got["authors"] == ["Jane Author"] and got["narrators"] == ["Joe Narrator"]
    assert got["cover_url"] == "https://cdn/1215.jpg"  # largest available
    assert got["series"] == [{"asin": "S001", "title": "Test Series", "sequence": "1"}]
    assert (got["rating"], got["date_added"], got["release_date"]) == (4.5, "2023-02-01", "2023-01-15")


def test_normalize_item_tolerates_missing_fields():
    got = normalize_item({"asin": "B002", "rating": None, "library_status": None})
    assert (got["title"], got["rating"], got["cover_url"], got["date_added"]) == ("", None, None, None)


# --- login -------------------------------------------------------------------------

def test_login_start_returns_amazon_url(tmp_path):
    url, state = LoginFlow(str(tmp_path)).start("uk", "Me")
    assert url.startswith("https://www.amazon.co.uk/ap/signin")
    assert state


def test_login_start_rejects_unknown_locale(tmp_path):
    with pytest.raises(LoginError):
        LoginFlow(str(tmp_path)).start("atlantis", "Me")


def test_login_complete_unknown_state(tmp_path):
    with pytest.raises(LoginError, match="unknown auth state"):
        LoginFlow(str(tmp_path)).complete("nope", "https://www.amazon.co.uk/ap/maplanding")


def test_login_complete_needs_code(tmp_path):
    flow = LoginFlow(str(tmp_path))
    _, state = flow.start("uk", "Me")
    with pytest.raises(LoginError, match="No authorization code"):
        flow.complete(state, "https://www.amazon.co.uk/ap/maplanding?foo=bar")


def test_login_complete_saves_tokens(tmp_path):
    flow = LoginFlow(str(tmp_path))
    _, state = flow.start("uk", "Me")
    registration = {"customer_info": {"user_id": "amzn1.account.ABC", "name": "Jo"}, "website_cookies": {"session-id": "1"}}
    with patch("app.audible_api.auth.register_", return_value=registration) as reg, \
         patch("app.audible_api.auth.storage.save_auth") as save:
        result = flow.complete(state, "https://www.amazon.co.uk/ap/maplanding?openid.oa2.authorization_code=CODE")
    assert reg.call_args.kwargs["authorization_code"] == "CODE"
    assert (result.account_id, result.email, result.name, result.locale) == ("amzn1.account.ABC", "amzn1.account.ABC", "Me", "uk")
    assert save.call_args.args[:2] == (str(tmp_path), "amzn1.account.ABC")
    # The state is single-use.
    with pytest.raises(LoginError):
        flow.complete(state, "https://www.amazon.co.uk/ap/maplanding?openid.oa2.authorization_code=CODE")


def test_largest_cover():
    from app.audible_api.content import largest_cover
    assert largest_cover({"product_images": {"500": "a", "2400": "b", "1215": "c"}}) == "b"
    assert largest_cover({"product_images": None}) == ""
