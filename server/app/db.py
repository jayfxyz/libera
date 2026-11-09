"""SQLite access.

One connection, guarded by a lock, shared by the request threadpool and the
download workers (which call it through ``asyncio.to_thread``). Queries are
small and local, so a single connection is plenty and keeps writes serialised
the way SQLite wants them.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


def iso_utc(value: str | None) -> str | None:
    """SQLite's CURRENT_TIMESTAMP text ("2026-11-08 23:00:51", UTC with no zone)
    as ISO 8601 with a Z, so browsers don't read it as local time. Values that
    already carry a zone or a T are returned unchanged."""
    if not value or "T" in value:
        return value
    return value.replace(" ", "T") + "Z"


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit; transaction() issues BEGIN itself.
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def migrate(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            # Columns added after the first release (SQLite has no ADD COLUMN IF NOT EXISTS).
            for statement in (
                "ALTER TABLE accounts ADD COLUMN last_scanned_at DATETIME",
                "ALTER TABLE library_books ADD COLUMN is_hidden INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE library_books ADD COLUMN file_path TEXT",
            ):
                try:
                    self._conn.execute(statement)
                except sqlite3.OperationalError:
                    pass  # already there

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        row = self.query_one(sql, params)
        return None if row is None else row[0]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Hold the lock and run statements atomically; rolls back on error."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    # --- settings --------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        return self.scalar("SELECT value FROM settings WHERE key = ?", (key,))

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def all_settings(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self.query("SELECT key, value FROM settings")}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
