"""Backend pieces behind the redesigned library: genres, hiding, account filter,
planned save path, bulk and PDF-only downloads."""

import asyncio
import os
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app import library
from app.db import Database
from app.main import create_app
from tests.conftest import add_account, make_book

LADDERS = [
    [{"id": "1", "name": "Health & Wellness"}, {"id": "2", "name": "Psychology & Mental Health"},
     {"id": "3", "name": "Psychology"}],
    [{"id": "4", "name": "Relationships"}, {"id": "5", "name": "Personal Development"}],
    [{"id": "1", "name": "Health & Wellness"}, {"id": "2", "name": "Psychology & Mental Health"},
     {"id": "3", "name": "Psychology"}],  # duplicate ladder
]


def test_genres_are_imported_and_replaced_on_rescan(db):
    add_account(db)
    library.import_library(db, 1, [make_book("A", genres=LADDERS)])
    book_id = db.scalar("SELECT id FROM books")
    assert library.genres(db, [book_id]) == {book_id: ["Psychology", "Personal Development"]}
    # Parents are kept as the tree.
    assert db.scalar("SELECT p.name FROM categories c JOIN categories p ON p.id = c.parent_id "
                     "WHERE c.name = 'Psychology'") == "Psychology & Mental Health"
    library.import_library(db, 1, [make_book("A", genres=[LADDERS[1]])])
    assert library.genres(db, [book_id]) == {book_id: ["Personal Development"]}


def test_list_has_people_genres_and_filters_by_account(db):
    add_account(db, 1)
    add_account(db, 2, "amzn1.account.OTHER")
    library.import_library(db, 1, [make_book("A", title="One", authors=["Au"], narrators=["Na"], genres=LADDERS)])
    library.import_library(db, 2, [make_book("B", title="Two")])
    rows = {b["audible_id"]: b for b in library.list_books(db)}
    assert (rows["A"]["authors"], rows["A"]["narrators"], rows["A"]["genres"]) == (
        ["Au"], ["Na"], ["Psychology", "Personal Development"])
    assert [b["audible_id"] for b in library.list_books(db, account_id=2)] == ["B"]
    assert [b["audible_id"] for b in library.list_books(db, search="one", account_id=2)] == []


def test_list_page_size(db):
    add_account(db)
    library.import_library(db, 1, [make_book(f"A{i:03d}") for i in range(120)])
    assert len(library.list_books(db)) == library.PAGE_SIZE
    assert len(library.list_books(db, limit=500)) == 120
    assert len(library.list_books(db, limit=100, page=2)) == 20


def test_migration_adds_columns_to_an_existing_database(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE library_books (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL, date_added DATETIME NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0,
        is_audible_plus INTEGER NOT NULL DEFAULT 0, liberation_status TEXT NOT NULL DEFAULT 'not_liberated',
        tags TEXT NOT NULL DEFAULT '', user_rating REAL, is_finished INTEGER NOT NULL DEFAULT 0,
        last_downloaded DATETIME, last_format TEXT, UNIQUE(book_id, account_id));""")
    old.close()
    db = Database(path)
    db.migrate()
    db.migrate()  # idempotent
    cols = {r["name"] for r in db.query("PRAGMA table_info(library_books)")}
    assert {"is_hidden", "file_path"} <= cols
    db.close()


@pytest.fixture
def api(config, db):
    jobs = []

    async def runner(queue, job):
        jobs.append(job)
        queue.set_status(job.id, "done", 100, "ok")

    with TestClient(create_app(config, db, runner=runner)) as c:
        c.jobs = jobs
        yield c


def seed(db):
    add_account(db)
    library.import_library(db, 1, [
        make_book("A", title="One", authors=["Jane Author"]),
        make_book("B", title="Two", authors=["Jane Author"]),
    ])
    return [r["id"] for r in db.query("SELECT id FROM books ORDER BY audible_id")]


def test_hide_one_and_many(api, db):
    a, b = seed(db)
    assert api.patch(f"/api/library/{a}", json={"is_hidden": True}).status_code == 204
    assert api.get(f"/api/library/{a}").json()["is_hidden"] is True
    assert api.post("/api/library/bulk", json={"book_ids": [a, b], "is_hidden": False}).status_code == 204
    assert {x["is_hidden"] for x in api.get("/api/library").json()} == {False}


def test_book_detail_has_planned_path_and_genres(api, db, config):
    a, _ = seed(db)
    detail = api.get(f"/api/library/{a}").json()
    assert detail["planned_path"] == os.path.join(config.output_dir, "Jane Author - One", "One.m4b")
    assert (detail["genres"], detail["file_path"], detail["is_hidden"]) == ([], None, False)
    library.mark_downloaded(db, a, "m4b", "/audiobooks/x/One.m4b")
    assert api.get(f"/api/library/{a}").json()["file_path"] == "/audiobooks/x/One.m4b"


def wait_for(api, n):
    for _ in range(100):
        if len(api.jobs) >= n:
            return
        time.sleep(0.02)
    raise AssertionError("jobs not run")


def test_bulk_download_and_options(api, db):
    a, b = seed(db)
    resp = api.post("/api/downloads/bulk", json={"book_ids": [b, a, b, 999], "kind": "pdf", "include_pdf": False})
    assert resp.status_code == 202
    assert [j["book_id"] for j in resp.json()["jobs"]] == [b, a]  # duplicate and unknown id skipped
    wait_for(api, 2)
    assert [(j.title, j.kind, j.include_pdf) for j in api.jobs] == [("Two", "pdf", False), ("One", "pdf", False)]
    assert {j["title"] for j in api.get("/api/downloads").json()} == {"One", "Two"}
    assert api.post("/api/downloads/bulk", json={"book_ids": [a], "kind": "video"}).status_code == 400


def test_single_download_needs_only_the_book_id(api, db):
    a, _ = seed(db)
    assert api.post("/api/downloads", json={"book_id": a}).status_code == 202
    wait_for(api, 1)
    assert (api.jobs[0].audible_id, api.jobs[0].audible_account_id, api.jobs[0].kind) == (
        "A", "amzn1.account.TEST", "audio")
