from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.audible_api.models import AudibleBook
from app.config import Config
from app.db import Database
from app.events import EventBus
from app.jobs.download import FileEntry, Target
from app.main import create_app
from app.services.library import LibraryService


@pytest.fixture
def db(tmp_path):
    # A file, like production: each thread gets its own connection (the queue
    # uses the database from the event loop and from worker threads).
    d = Database(str(tmp_path / "test.db"))
    d.migrate()
    yield d
    d.close()


@pytest.fixture
def config(tmp_path):
    return Config(
        database_path=":memory:",
        accounts_dir=str(tmp_path / "accounts"),
        output_dir=str(tmp_path / "audiobooks"),
    )


@pytest.fixture
def client(config, db):
    with TestClient(create_app(config, db)) as c:
        yield c


def add_account(db, account_id: int = 1, audible_account_id: str = "amzn1.account.TEST") -> int:
    db.execute(
        "INSERT INTO accounts (id, account_name, email, locale, audible_account_id) VALUES (?, ?, ?, 'uk', ?)",
        (account_id, f"Account {account_id}", f"user{account_id}@example.com", audible_account_id),
    )
    return account_id


@pytest.fixture
def library_svc(db, config):
    return LibraryService(db, config, EventBus())


def import_books(db, account_id: int, books: list[AudibleBook]) -> int:
    """Test setup: import books for an account as a library scan would."""
    return LibraryService(db, Config(), EventBus()).import_library(account_id, books)


def make_book(asin: str, **overrides) -> AudibleBook:
    """A library item as the Audible sync gives it; unknown fields are an error."""
    return AudibleBook(**{"asin": asin, "title": f"Book {asin}", "runtime_length_min": 60,
                          "date_added": "2024-01-01", **overrides})


class FakePipeline:
    """Stands in for the real pipeline (Audible + ffmpeg) and records the
    targets it ran. on_fetch / on_decrypt, async (target, report_progress),
    change what a step does. Its fetch leaves a bundle like the real one."""

    def __init__(self):
        self.fetched: list[Target] = []
        self.decrypted: list[Target] = []
        self.on_fetch = None
        self.on_decrypt = None

    async def fetch(self, t, work_dir, report_progress):
        self.fetched.append(t)
        report_progress("downloading", 50)
        if self.on_fetch:
            await self.on_fetch(t, report_progress)
        os.makedirs(work_dir, exist_ok=True)
        with open(os.path.join(work_dir, f"{t.download_id}.license.json"), "w") as f:
            json.dump({"format": "aaxc", "key": "k", "iv": "i"}, f)
        open(os.path.join(work_dir, f"{t.download_id}.aaxc"), "wb").close()

    async def decrypt(self, t, work_dir, report_progress):
        self.decrypted.append(t)
        if self.on_decrypt:
            await self.on_decrypt(t, report_progress)
        return [FileEntry("audio", f"{t.base_name}.{t.format}", 1)]


@pytest.fixture
def pipeline():
    return FakePipeline()


def wait_until(predicate, timeout=3.0):
    """For tests on the TestClient's side (the app runs in another thread)."""
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)
