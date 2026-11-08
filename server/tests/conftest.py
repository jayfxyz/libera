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
