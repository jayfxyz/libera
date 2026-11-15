"""Audible accounts: listing, logging in, scanning, renaming, removing."""

from __future__ import annotations

import asyncio
from typing import Any

from ..audible_api.client import AudibleClient
from ..audible_api.storage import AccountNotFound
from ..db import Database, iso_utc
from ..repositories import accounts as repo
from .library import LibraryService


class ScanFailed(Exception):
    """Audible couldn't return the account's library."""


class AccountsService:
    def __init__(self, db: Database, audible: AudibleClient, library: LibraryService):
        self._db = db
        self._audible = audible
        self._library = library

    def list(self) -> list[dict[str, Any]]:
        with self._db.session() as s:
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

    def start_login(self, locale: str, name: str) -> tuple[str, str]:
        """The Amazon sign-in URL and the state to complete it with (blocking).
        Raises audible_api.auth.LoginError."""
        return self._audible.start_login(locale, name)

    def complete_login(self, state: str, response_url: str) -> str:
        """Finish a login (blocking network call) and save the account. Returns its email/id.
        Raises audible_api.auth.LoginError."""
        result = self._audible.complete_login(state, response_url)
        with self._db.session() as s:
            repo.save_login(s, name=result.name, email=result.email, locale=result.locale,
                            audible_account_id=result.account_id)
        return result.email

    def rename(self, account_id: int, name: str) -> None:
        with self._db.session() as s:
            repo.rename(s, account_id, name)

    def remove(self, account_id: int) -> None:
        with self._db.session() as s:
            repo.delete_with_library(s, account_id)

    async def scan(self, account_id: int) -> int | None:
        """Fetch the account's Audible library and import it. None if there's no such
        account; raises AccountNotFound (no saved login) or ScanFailed."""
        key = await asyncio.to_thread(self._audible_account_id, account_id)
        if key is None:
            return None
        try:
            books = await self._audible.get_library(key)
        except AccountNotFound:
            raise
        except Exception as e:
            raise ScanFailed(f"Audible library fetch failed: {e}") from e
        imported = await asyncio.to_thread(self._library.import_library, account_id, books)
        await asyncio.to_thread(self._mark_scanned, account_id)
        return imported

    def _audible_account_id(self, account_id: int) -> str | None:
        with self._db.session() as s:
            account = repo.get(s, account_id)
            return account.audible_account_id if account else None

    def _mark_scanned(self, account_id: int) -> None:
        with self._db.session() as s:
            repo.mark_scanned(s, account_id)
