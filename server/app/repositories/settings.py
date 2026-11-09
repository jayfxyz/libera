"""User settings: a key/value table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..db.models import Setting


def get(s: Session, key: str) -> str | None:
    return s.scalar(select(Setting.value).where(Setting.key == key))


def set(s: Session, key: str, value: str) -> None:  # noqa: A001 - mirrors get()
    stmt = insert(Setting).values(key=key, value=value)
    s.execute(stmt.on_conflict_do_update(index_elements=[Setting.key], set_={"value": value}))


def all(s: Session) -> dict[str, str]:  # noqa: A001
    return {row.key: row.value for row in s.scalars(select(Setting))}
