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


def find_login(s: Session, *, email: str, locale: str) -> Account | None:
    """The account for this Amazon login in this region, if it was added before."""
    return s.scalar(select(Account).where(Account.email == email, Account.locale == locale))


def save_login(s: Session, *, name: str, email: str, locale: str, audible_account_id: str) -> int:
    """Add an account, or update it when the same Amazon login is added again in the
    same region (another region is another account). Returns the account's id."""
    stmt = insert(Account).values(account_name=name, email=email, locale=locale,
                                  audible_account_id=audible_account_id)
    return s.scalar(stmt.on_conflict_do_update(
        index_elements=[Account.email, Account.locale],
        set_={
            "account_name": stmt.excluded.account_name,
            "audible_account_id": stmt.excluded.audible_account_id,
        },
    ).returning(Account.id))


def rename(s: Session, account_id: int, name: str) -> None:
    s.execute(update(Account).where(Account.id == account_id).values(account_name=name))


def delete_with_library(s: Session, account_id: int) -> None:
    """Remove an account and its library entries (the books themselves stay)."""
    s.execute(delete(LibraryBook).where(LibraryBook.account_id == account_id))
    s.execute(delete(Account).where(Account.id == account_id))


def mark_scanned(s: Session, account_id: int) -> None:
    s.execute(update(Account).where(Account.id == account_id).values(last_scanned_at=func.current_timestamp()))
