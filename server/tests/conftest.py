from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.db import Database
from app.main import create_app


@pytest.fixture
def db():
    d = Database(":memory:")
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


def make_book(asin: str, **overrides) -> dict:
    book = {
        "asin": asin,
        "title": f"Book {asin}",
        "subtitle": None,
        "description": None,
        "runtime_length_min": 60,
        "authors": [],
        "narrators": [],
        "publisher_name": None,
        "cover_url": None,
        "language": None,
        "release_date": None,
        "series": [],
        "rating": None,
        "is_plus_catalog_item": False,
        "date_added": "2024-01-01",
    }
    book.update(overrides)
    return book
