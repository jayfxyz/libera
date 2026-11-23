import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.audible_api.auth import LoginError, LoginResult
from app.config import NamingPreset
from app.jobs.download import DownloadFailed
from app.main import create_app
from tests.conftest import add_account, make_book, import_books


@pytest.fixture
def audible():
    a = MagicMock()
    a.start_login.return_value = ("https://www.amazon.co.uk/ap/signin?x", "state-1")
    a.complete_login.return_value = LoginResult("amzn1.account.NEW", "me@example.com", "Mine", "uk")
    a.get_library = AsyncMock(return_value=[make_book("A1", title="Scanned")])
    return a


@pytest.fixture
def api(config, db, audible, pipeline):
    async def slow_titles_hang(t, report):
        if t.title == "Slow":
            await asyncio.sleep(60)

    pipeline.on_fetch = slow_titles_hang
    with TestClient(create_app(config, db, audible=audible, pipeline=pipeline)) as c:
        yield c


# --- accounts ------------------------------------------------------------------

def test_login_flow_creates_account(api, audible):
    assert api.post("/api/accounts/auth/start", json={"locale": "uk", "name": "Mine"}).json() == {
        "auth_url": "https://www.amazon.co.uk/ap/signin?x", "state": "state-1"}
    resp = api.post("/api/accounts/auth/complete", json={"state": "state-1", "response_url": "https://x"})
    accounts = api.get("/api/accounts").json()
    assert resp.json() == {"id": accounts[0]["id"], "email": "me@example.com"}
    assert [(a["account_name"], a["email"], a["locale"], a["library_scan_enabled"]) for a in accounts] == [
        ("Mine", "me@example.com", "uk", True)]
    audible.save_login.assert_called_once_with("amzn1.account.NEW-uk", None)


def login(api, audible, locale, name="Mine"):
    audible.complete_login.return_value = LoginResult("amzn1.account.NEW", "me@example.com", name, locale)
    return api.post("/api/accounts/auth/complete", json={"state": "s", "response_url": "https://x"}).json()


def test_one_login_in_two_regions_is_two_accounts_with_their_own_token_files(api, audible):
    uk, us = login(api, audible, "uk"), login(api, audible, "us", name="Mine US")
    assert uk["id"] != us["id"]
    assert [(a["account_name"], a["locale"]) for a in api.get("/api/accounts").json()] == [
        ("Mine", "uk"), ("Mine US", "us")]
    assert [c.args[0] for c in audible.save_login.call_args_list] == ["amzn1.account.NEW-uk", "amzn1.account.NEW-us"]

    # Logging in to the UK again updates that account and replaces only the UK login.
    assert login(api, audible, "uk", name="Renamed")["id"] == uk["id"]
    assert audible.save_login.call_args.args[0] == "amzn1.account.NEW-uk"
    assert [a["account_name"] for a in api.get("/api/accounts").json()] == ["Renamed", "Mine US"]


def test_an_account_added_before_regions_keeps_its_token_file(api, db, audible):
    db.execute("INSERT INTO accounts (account_name, email, locale, audible_account_id) "
               "VALUES ('Old', 'me@example.com', 'uk', 'amzn1.account.NEW')")
    login(api, audible, "uk")
    assert audible.save_login.call_args.args[0] == "amzn1.account.NEW"
    assert len(api.get("/api/accounts").json()) == 1


def test_login_errors(api, audible):
    assert api.post("/api/accounts/auth/complete", json={"state": "", "response_url": ""}).status_code == 400
    audible.complete_login.side_effect = LoginError("unknown auth state — try starting login again")
    resp = api.post("/api/accounts/auth/complete", json={"state": "x", "response_url": "https://x"})
    assert resp.status_code == 400 and "unknown auth state" in resp.text


def test_rename_scan_and_delete_account(api, db, audible):
    add_account(db)
    assert api.patch("/api/accounts/1", json={"account_name": "Renamed"}).status_code == 204
    assert api.get("/api/accounts").json()[0]["account_name"] == "Renamed"

    assert api.post("/api/accounts/1/scan").json() == {"imported": 1}
    audible.get_library.assert_awaited_with("amzn1.account.TEST")
    assert api.get("/api/accounts").json()[0]["last_scanned_at"]
    assert [b["title"] for b in api.get("/api/library").json()] == ["Scanned"]
    assert api.post("/api/accounts/99/scan").status_code == 404

    assert api.delete("/api/accounts/1").status_code == 204
    assert api.get("/api/accounts").json() == []
    assert api.get("/api/library").json() == []


# --- downloads ---------------------------------------------------------------

def seed(db, title="The Book"):
    add_account(db)
    import_books(db, 1, [make_book(
        "B0001", title=title, authors=["Jane Author"], release_date="2007-03-27", date_added="2024-01-01",
        runtime_length_min=125, series=[{"asin": "S1", "title": "Saga", "sequence": "1"}])])
    return db.scalar("SELECT id FROM books")


def wait_finished(api, download_id):
    for _ in range(150):
        job = next(j for j in api.get("/api/downloads").json() if j["id"] == download_id)
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("download did not finish")


def test_enqueue_names_the_download_from_book_and_settings(api, db, config, pipeline):
    book_id = seed(db)
    config.naming = NamingPreset.AUTHOR_SERIES_YEAR
    resp = api.post("/api/downloads", json={"book_id": book_id, "audible_id": "B0001", "account_id": 1})
    assert resp.status_code == 202
    job = wait_finished(api, resp.json()["id"])
    assert job.pop("created_at").endswith("Z") and job.pop("finished_at").endswith("Z")
    assert job.pop("updated_at").endswith("Z")
    book_dir = os.path.join(config.output_dir, "Jane Author", "Saga", "1 - 2007 - The Book")
    base = "The Book"
    assert job == {"id": resp.json()["id"], "book_id": book_id, "title": "The Book", "format": "m4b",
                   "status": "done", "percent": 100, "message": os.path.join(book_dir, f"{base}.m4b"),
                   "files": [{"role": "audio", "name": f"{base}.m4b", "size_bytes": 1}]}
    t = pipeline.decrypted[0]
    assert (t.path, t.base_name, t.audible_id, t.audible_account_id) == (
        book_dir, base, "B0001", "amzn1.account.TEST")


def test_enqueue_validation(api, db):
    seed(db)
    assert api.post("/api/downloads", json={"book_id": 999, "audible_id": "X", "account_id": 1}).status_code == 404
    assert api.post("/api/downloads", json={"book_id": 1, "audible_id": "B0001", "account_id": 1,
                                            "format": "wav"}).status_code == 400


def test_cancel_download(api, db):
    book_id = seed(db, title="Slow")
    download_id = api.post("/api/downloads", json={"book_id": book_id, "audible_id": "B0001", "account_id": 1}).json()["id"]
    assert api.delete(f"/api/downloads/{download_id}").status_code == 204  # queued or running, both cancel
    job = wait_finished(api, download_id)
    assert job["status"] == "cancelled" and "message" not in job
    assert api.delete(f"/api/downloads/{download_id}").status_code == 404


def test_retry_a_failed_download(api, db, pipeline):
    failures = ["ffmpeg: boom"]

    async def broken_once(t, report):
        if failures:
            raise DownloadFailed(failures.pop())

    pipeline.on_decrypt = broken_once
    download_id = api.post("/api/downloads", json={"book_id": seed(db)}).json()["id"]
    assert wait_finished(api, download_id)["message"] == "ffmpeg: boom"
    assert api.post(f"/api/downloads/{download_id}/retry").status_code == 202
    assert wait_finished(api, download_id)["status"] == "done"
    assert (len(pipeline.fetched), len(pipeline.decrypted)) == (1, 2)
    assert api.post(f"/api/downloads/{download_id}/retry").status_code == 404

