"""Alembic environment. Migrations run at app startup (db/migrate.py), which
passes its own connection; the CLI (alembic.ini) uses DATABASE_PATH."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from app.db.migrations_env_filter import include_object
from app.db.models import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        render_as_batch=True,  # SQLite can't ALTER most things; Alembic rebuilds the table instead
        compare_type=False,  # dates are text in SQLite but DATETIME in the DDL; not a real difference
    )
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    _configure(connection)
else:
    url = config.get_main_option("sqlalchemy.url") or f"sqlite:///{os.environ.get('DATABASE_PATH', './data/db/libation.db')}"
    with create_engine(url).connect() as conn:
        _configure(conn)
