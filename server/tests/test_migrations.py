"""Migrations run against databases built at an older revision."""

import json

import pytest
from alembic import command

from app.db import Database
from app.db.migrate import _config


def at_revision(tmp_path, revision: str) -> Database:
    db = Database(str(tmp_path / "t.db"))
    with db.engine.begin() as conn:
        command.upgrade(_config(conn), revision)
    return db


def add_job(db, id, status, message, **payload):
    payload = {"book_id": 10, "account_id": 1, "format": "m4b", "split_chapters": False, **payload}
    column_book = payload["book_id"] if payload["book_id"] in (10, 11) else None  # SET NULL when a book went
    db.execute("INSERT INTO jobs (id, type, status, message, title, book_id, payload, started_at, finished_at) "
               "VALUES (?, 'download', ?, ?, 'T', ?, ?, '2026-01-01 10:00:00', '2026-01-01 10:05:00')",
               (id, status, message, column_book, json.dumps(payload)))


def test_0004_turns_finished_audio_jobs_into_downloads(tmp_path):
    db = at_revision(tmp_path, "0003")
    db.execute("INSERT INTO accounts (id, account_name, email, locale) VALUES (1, 'A', 'a@x', 'uk')")
    db.execute("INSERT INTO books (id, audible_id, title, locale) VALUES (10, 'B1', 'One', 'uk'), (11, 'B2', 'Two', 'uk')")
    db.execute("INSERT INTO library_books (id, book_id, account_id, date_added) "
               "VALUES (100, 10, 1, '2024-01-01'), (101, 11, 1, '2024-01-01')")
    add_job(db, "done-audio", "done", "/audiobooks/Jane - One/One.m4b", kind="audio", split_chapters=True)
    add_job(db, "done-no-kind", "done", "/audiobooks/Two.mp3", book_id=11, format="mp3")  # before `kind` existed
    add_job(db, "done-pdf", "done", "/audiobooks/Jane - One/One.pdf", kind="pdf")
    add_job(db, "failed", "error", "ffmpeg: boom")
    add_job(db, "cancelled", "error", "Cancelled")
    add_job(db, "queued", "queued", None)
    add_job(db, "book-gone", "done", "/audiobooks/Gone.m4b", book_id=99)

    db.migrate()

    rows = {r["id"]: dict(r) for r in db.query(
        "SELECT id, library_book_id, format, split_chapters, path, base_name, status, percent, files FROM downloads")}
    assert rows == {
        "done-audio": {"id": "done-audio", "library_book_id": 100, "format": "m4b", "split_chapters": 1,
                       "path": "/audiobooks/Jane - One", "base_name": "One", "status": "done", "percent": 100.0,
                       "files": None},
        "done-no-kind": {"id": "done-no-kind", "library_book_id": 101, "format": "mp3", "split_chapters": 0,
                         "path": "/audiobooks", "base_name": "Two", "status": "done", "percent": 100.0,
                         "files": None},
    }
    assert db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE name = 'jobs'") == 0
    db.close()


def test_0004_downgrades_cleanly(tmp_path):
    db = at_revision(tmp_path, "head")
    db.execute("INSERT INTO tasks (id, type, payload, status) VALUES ('t1', 'x', '{}', 'completed')")
    with db.engine.begin() as conn:
        command.downgrade(_config(conn), "0003")
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "jobs" in names and "downloads" not in names
    assert "has_pdf" not in {c["name"] for c in db.query("PRAGMA table_info(books)")}
    db.execute("UPDATE tasks SET status = 'anything'")  # the enum's CHECK went with the downgrade
    db.execute("UPDATE tasks SET status = 'completed'")
    db.migrate()  # and up again
    assert db.scalar("SELECT version_num FROM alembic_version") == "0006"
    db.close()


def test_0005_backfills_updated_at(tmp_path):
    db = at_revision(tmp_path, "0004")
    db.execute("INSERT INTO accounts (id, account_name, email, locale) VALUES (1, 'A', 'a@x', 'uk')")
    db.execute("INSERT INTO books (id, audible_id, title, locale) VALUES (10, 'B1', 'One', 'uk')")
    db.execute("INSERT INTO library_books (id, book_id, account_id, date_added, last_downloaded) "
               "VALUES (100, 10, 1, '2024-01-01', '2026-01-02 03:04:05')")
    db.execute("INSERT INTO downloads (id, library_book_id, format, path, base_name, status, created_at, finished_at) "
               "VALUES ('d1', 100, 'm4b', '/p', 'One', 'done', '2026-01-01 00:00:00', '2026-01-01 00:10:00')")
    db.migrate()
    assert db.scalar("SELECT updated_at FROM downloads") == "2026-01-01 00:10:00"
    assert db.scalar("SELECT updated_at FROM library_books") == "2026-01-02 03:04:05"
    db.close()


def test_0006_allows_one_login_in_several_regions_and_keeps_everything(tmp_path):
    db = at_revision(tmp_path, "0005")
    db.execute("INSERT INTO accounts (id, account_name, email, locale, audible_account_id, last_scanned_at) "
               "VALUES (1, 'A', 'amzn1.account.X', 'uk', 'amzn1.account.X', '2026-01-01 00:00:00'), "
               "(7, 'B', 'b@x', 'us', 'b', NULL)")
    db.execute("DELETE FROM accounts WHERE id = 7")  # the next account must not get id 7 again
    db.execute("INSERT INTO books (id, audible_id, title, locale) VALUES (10, 'B1', 'One', 'uk')")
    db.execute("INSERT INTO library_books (id, book_id, account_id, date_added) VALUES (100, 10, 1, '2024-01-01')")
    db.migrate()  # the app's path: foreign keys off while the table is rebuilt

    assert db.query_one("SELECT account_name, audible_account_id, last_scanned_at FROM accounts WHERE id = 1") == {
        "account_name": "A", "audible_account_id": "amzn1.account.X", "last_scanned_at": "2026-01-01 00:00:00"}
    assert db.scalar("SELECT account_id FROM library_books WHERE id = 100") == 1
    db.execute("INSERT INTO accounts (account_name, email, locale) VALUES ('A US', 'amzn1.account.X', 'us')")
    assert db.scalar("SELECT max(id) FROM accounts") == 8
    with pytest.raises(Exception):  # the same login and region twice is still refused
        db.execute("INSERT INTO accounts (account_name, email, locale) VALUES ('A', 'amzn1.account.X', 'uk')")
    assert db.query("PRAGMA foreign_key_check") == []
    assert db.scalar("PRAGMA foreign_keys") == 1  # back on after migrating
    db.close()


def test_a_legacy_libation_db_is_moved_to_the_new_name(tmp_path):
    legacy = Database(str(tmp_path / "libation.db"))
    legacy.migrate()
    legacy.execute("INSERT INTO accounts (id, account_name, email, locale) VALUES (1, 'A', 'a@x', 'uk')")
    legacy.close()
    (tmp_path / "libation.db-wal").write_bytes(b"")  # a leftover WAL goes with it
    db = Database(str(tmp_path / "libera.db"))
    assert db.scalar("SELECT account_name FROM accounts") == "A"
    assert not (tmp_path / "libation.db").exists() and not (tmp_path / "libation.db-wal").exists()
    db.close()


def test_an_existing_libera_db_wins_over_a_legacy_one(tmp_path):
    current = Database(str(tmp_path / "libera.db"))
    current.migrate()
    current.close()
    (tmp_path / "libation.db").write_bytes(b"old")
    db = Database(str(tmp_path / "libera.db"))
    assert db.scalar("SELECT version_num FROM alembic_version")  # still the real database
    db.close()
    assert (tmp_path / "libation.db").read_bytes() == b"old"  # left alone
