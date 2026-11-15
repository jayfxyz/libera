"""Backend pieces behind the redesigned library: genres, hiding, account filter,
planned save path, bulk downloads."""

import asyncio
import os
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.services import library
from app.db import Database
from app.main import create_app
from tests.conftest import add_account, make_book, wait_until, import_books

LADDERS = [
    [{"id": "1", "name": "Health & Wellness"}, {"id": "2", "name": "Psychology & Mental Health"},
     {"id": "3", "name": "Psychology"}],
    [{"id": "4", "name": "Relationships"}, {"id": "5", "name": "Personal Development"}],
    [{"id": "1", "name": "Health & Wellness"}, {"id": "2", "name": "Psychology & Mental Health"},
     {"id": "3", "name": "Psychology"}],  # duplicate ladder
]


def test_genres_are_imported_and_replaced_on_rescan(db, library_svc):
    add_account(db)
    import_books(db, 1, [make_book("A", genres=LADDERS)])
    book_id = db.scalar("SELECT id FROM books")
    assert library_svc.genres([book_id]) == {book_id: ["Psychology", "Personal Development"]}
    # Parents are kept as the tree.
    assert db.scalar("SELECT p.name FROM categories c JOIN categories p ON p.id = c.parent_id "
                     "WHERE c.name = 'Psychology'") == "Psychology & Mental Health"
    import_books(db, 1, [make_book("A", genres=[LADDERS[1]])])
    assert library_svc.genres([book_id]) == {book_id: ["Personal Development"]}


def test_list_has_people_genres_and_filters_by_account(db, library_svc):
    add_account(db, 1)
    add_account(db, 2, "amzn1.account.OTHER")
    import_books(db, 1, [make_book("A", title="One", authors=["Au"], narrators=["Na"], genres=LADDERS)])
    import_books(db, 2, [make_book("B", title="Two")])
    rows = {b["audible_id"]: b for b in library_svc.list_books()}
    assert (rows["A"]["authors"], rows["A"]["narrators"], rows["A"]["genres"]) == (
        ["Au"], ["Na"], ["Psychology", "Personal Development"])
    assert [b["audible_id"] for b in library_svc.list_books(account_id=2)] == ["B"]
    assert [b["audible_id"] for b in library_svc.list_books(search="one", account_id=2)] == []


def test_list_page_size(db, library_svc):
    add_account(db)
    import_books(db, 1, [make_book(f"A{i:03d}") for i in range(120)])
    assert len(library_svc.list_books()) == library.PAGE_SIZE
    assert len(library_svc.list_books(limit=500)) == 120
    assert len(library_svc.list_books(limit=100, page=2)) == 20


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
def api(config, db, pipeline):
    with TestClient(create_app(config, db, pipeline=pipeline)) as c:
        yield c


def seed(db):
    add_account(db)
    import_books(db, 1, [
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


def test_book_detail_has_planned_path_and_genres(api, db, config, library_svc):
    a, _ = seed(db)
    detail = api.get(f"/api/library/{a}").json()
    assert detail["planned_path"] == os.path.join(config.output_dir, "Jane Author - One", "One.m4b")
    assert (detail["genres"], detail["file_path"], detail["is_hidden"]) == ([], None, False)
    library_svc.mark_downloaded(a, "m4b", "/audiobooks/x/One.m4b")
    assert api.get(f"/api/library/{a}").json()["file_path"] == "/audiobooks/x/One.m4b"


def test_bulk_download_and_options(api, db, pipeline):
    a, b = seed(db)
    resp = api.post("/api/downloads/bulk", json={"book_ids": [b, a, b, 999], "format": "mp3", "split_chapters": True})
    assert resp.status_code == 202
    assert [j["book_id"] for j in resp.json()["jobs"]] == [b, a]  # duplicate and unknown id skipped
    wait_until(lambda: len(pipeline.decrypted) == 2)
    # Three workers may start them in any order; the queue order is the response's.
    assert sorted((t.title, t.format, t.split_chapters) for t in pipeline.decrypted) == [
        ("One", "mp3", True), ("Two", "mp3", True)]
    assert {j["title"] for j in api.get("/api/downloads").json()} == {"One", "Two"}
    assert api.post("/api/downloads/bulk", json={"book_ids": [a], "format": "wav"}).status_code == 400


def test_single_download_needs_only_the_book_id(api, db, pipeline):
    a, _ = seed(db)
    assert api.post("/api/downloads", json={"book_id": a}).status_code == 202
    wait_until(lambda: pipeline.fetched)
    assert (pipeline.fetched[0].audible_id, pipeline.fetched[0].audible_account_id) == ("A", "amzn1.account.TEST")


def test_pre_alembic_database_with_data_is_adopted_in_place(tmp_path):
    """A database made by the old schema.sql (with data) is stamped, upgraded and keeps its rows."""
    path = str(tmp_path / "legacy.db")
    legacy = sqlite3.connect(path)
    legacy.executescript("""
        CREATE TABLE accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, account_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE, locale TEXT NOT NULL, audible_account_id TEXT NOT NULL DEFAULT '',
            library_scan_enabled INTEGER NOT NULL DEFAULT 1, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO accounts (account_name, email, locale) VALUES ('Old', 'old@example.com', 'uk');
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO settings VALUES ('default_format', 'mp3');
    """)
    legacy.close()

    db = Database(path)
    db.migrate()
    assert db.scalar("SELECT account_name FROM accounts") == "Old"
    assert db.scalar("SELECT value FROM settings WHERE key = 'default_format'") == "mp3"
    assert db.scalar("SELECT version_num FROM alembic_version") is not None
    cols = {r["name"] for r in db.query("PRAGMA table_info(accounts)")}
    assert "last_scanned_at" in cols
    # Tables the old database lacked exist now (incl. the search index).
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"books", "library_books", "books_fts", "categories"} <= names
    db.close()


def test_fresh_database_matches_the_models(tmp_path):
    """Migrations and models agree (so future autogenerated migrations start clean)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.models import Base

    db = Database(str(tmp_path / "fresh.db"))
    db.migrate()
    from app.db.migrations_env_filter import include_object

    with db.engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": False, "include_object": include_object})
        diff = compare_metadata(ctx, Base.metadata)

    def pk_nullable_quirk(d):
        # SQLite reports "INTEGER PRIMARY KEY" columns (no explicit NOT NULL) as nullable.
        return isinstance(d, list) and d[0][0] == "modify_nullable" and d[0][3] in ("id", "key")

    real = [d for d in diff if not pk_nullable_quirk(d)]
    assert real == [], real
    db.close()
