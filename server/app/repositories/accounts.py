"""Audible accounts."""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..db.models import Account, LibraryBook


def list_all(s: Session) -> list[Account]:
    return list(s.scalars(select(Account).order_by(Account.id)))


def get(s: Session, account_id: int) -> Account | None:
    return s.get(Account, account_id)


def save_login(s: Session, *, name: str, email: str, locale: str, audible_account_id: str) -> None:
    """Add an account, or update it when the same Amazon login is added again."""
    stmt = insert(Account).values(account_name=name, email=email, locale=locale,
                                  audible_account_id=audible_account_id)
    s.execute(stmt.on_conflict_do_update(
        index_elements=[Account.email],
        set_={
            "account_name": stmt.excluded.account_name,
            "locale": stmt.excluded.locale,  # the saved login is for this region now
            "audible_account_id": stmt.excluded.audible_account_id,
        },
    ))


def rename(s: Session, account_id: int, name: str) -> None:
    s.execute(update(Account).where(Account.id == account_id).values(account_name=name))


def delete_with_library(s: Session, account_id: int) -> None:
    """Remove an account and its library entries (the books themselves stay)."""
    s.execute(delete(LibraryBook).where(LibraryBook.account_id == account_id))
    s.execute(delete(Account).where(Account.id == account_id))


def mark_scanned(s: Session, account_id: int) -> None:
    s.execute(update(Account).where(Account.id == account_id).values(last_scanned_at=func.current_timestamp()))
