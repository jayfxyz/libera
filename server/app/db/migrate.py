"""Bring the database schema up to date at startup."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect

log = logging.getLogger(__name__)

MIGRATIONS = Path(__file__).parent / "migrations"
BASELINE = "0001"

# Columns added before Alembic existed. A database created then may lack some;
# they're added before it is stamped as the baseline.
_PRE_ALEMBIC_COLUMNS = [
    ("accounts", "last_scanned_at", "DATETIME"),
    ("library_books", "is_hidden", "INTEGER NOT NULL DEFAULT 0"),
    ("library_books", "file_path", "TEXT"),
]


def _config(connection: Connection) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["connection"] = connection
    return cfg


def upgrade(engine: Engine) -> None:
    """Adopt a pre-Alembic database if needed, then upgrade to the latest revision."""
    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if "alembic_version" not in tables and tables & _baseline_tables():
            _adopt(conn)
        command.upgrade(_config(conn), "head")


def _baseline():
    """The baseline migration module (its file name isn't importable as a module name)."""
    spec = importlib.util.spec_from_file_location("baseline", MIGRATIONS / "versions" / "0001_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _baseline_tables() -> set[str]:
    return set(_baseline().TABLES)


def _adopt(conn: Connection) -> None:
    """A database created before Alembic: complete it to the baseline and mark it so.

    Missing tables are created (CREATE ... IF NOT EXISTS of the baseline) and
    columns added since the first release are added; existing data is untouched.
    """
    for statement in _baseline().STATEMENTS:
        conn.exec_driver_sql(statement.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS")
                             .replace("CREATE VIRTUAL TABLE", "CREATE VIRTUAL TABLE IF NOT EXISTS"))
    inspector = inspect(conn)
    for table, column, ddl in _PRE_ALEMBIC_COLUMNS:
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    command.stamp(_config(conn), BASELINE)
    log.info("adopted an existing database as migration %s", BASELINE)
