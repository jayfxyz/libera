"""Database access: a SQLAlchemy engine, sessions and migrations.

Application code reads and writes through the repositories
(app/repositories), each taking a Session from ``Database.session()``.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from . import migrate


def iso_utc(value: str | None) -> str | None:
    """SQLite's CURRENT_TIMESTAMP text ("2026-11-08 23:00:51", UTC with no zone)
    as ISO 8601 with a Z, so browsers don't read it as local time. Values that
    already carry a zone or a T are returned unchanged."""
    if not value or "T" in value:
        return value
    return value.replace(" ", "T") + "Z"


def _sqlite_engine(path: str) -> Engine:
    if path == ":memory:":
        # One shared connection, or every session would see its own empty database.
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        if path != ":memory:":
            cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


class Database:
    def __init__(self, path: str):
        self.engine = _sqlite_engine(path)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self) -> None:
        migrate.upgrade(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """A unit of work: committed if the block succeeds, rolled back if it raises."""
        with self._sessions() as session, session.begin():
            yield session

    def close(self) -> None:
        self.engine.dispose()

    # --- raw SQL, for tests and maintenance scripts (the app uses repositories) ---

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        with self.engine.begin() as conn:
            return conn.exec_driver_sql(sql, tuple(params))

    def query(self, sql: str, params: tuple | list = ()) -> list[Any]:
        with self.engine.connect() as conn:
            return list(conn.exec_driver_sql(sql, tuple(params)).mappings())

    def query_one(self, sql: str, params: tuple | list = ()) -> Any:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        with self.engine.connect() as conn:
            return conn.exec_driver_sql(sql, tuple(params)).scalar()
