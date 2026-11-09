"""Audible accounts: listing, logging in, scanning, renaming, removing."""

from __future__ import annotations

from typing import Any

from ..audible_api.client import AudibleClient
from ..audible_api.storage import AccountNotFound
from ..db import Database, iso_utc
from ..repositories import accounts as repo
from . import library


class ScanFailed(Exception):
    """Audible couldn't return the account's library."""


def list_accounts(db: Database) -> list[dict[str, Any]]:
    with db.session() as s:
        return [
            {
                "id": a.id,
                "account_name": a.account_name,
                "email": a.email,
                "locale": a.locale,
                "library_scan_enabled": bool(a.library_scan_enabled),
                "last_scanned_at": iso_utc(a.last_scanned_at),
            }
            for a in repo.list_all(s)
        ]


def complete_login(db: Database, audible: AudibleClient, state: str, response_url: str) -> str:
    """Finish a login (blocking network call) and save the account. Returns its email/id.
    Raises audible_api.auth.LoginError."""
    result = audible.complete_login(state, response_url)
    with db.session() as s:
        repo.save_login(s, name=result.name, email=result.email, locale=result.locale,
                        audible_account_id=result.account_id)
    return result.email


def rename(db: Database, account_id: int, name: str) -> None:
    with db.session() as s:
        repo.rename(s, account_id, name)


def remove(db: Database, account_id: int) -> None:
    with db.session() as s:
        repo.delete_with_library(s, account_id)


def audible_account_id(db: Database, account_id: int) -> str | None:
    with db.session() as s:
        account = repo.get(s, account_id)
        return account.audible_account_id if account else None


async def scan(db: Database, audible: AudibleClient, account_id: int) -> int | None:
    """Fetch the account's Audible library and import it. None if there's no such
    account; raises AccountNotFound (no saved login) or ScanFailed."""
    import asyncio

    key = await asyncio.to_thread(audible_account_id, db, account_id)
    if key is None:
        return None
    try:
        books = await audible.get_library(key)
    except AccountNotFound:
        raise
    except Exception as e:
        raise ScanFailed(f"Audible library fetch failed: {e}") from e
    imported = await asyncio.to_thread(library.import_library, db, account_id, books)
    await asyncio.to_thread(_mark_scanned, db, account_id)
    return imported


def _mark_scanned(db: Database, account_id: int) -> None:
    with db.session() as s:
        repo.mark_scanned(s, account_id)
