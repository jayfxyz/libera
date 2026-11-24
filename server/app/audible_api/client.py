"""The one object the rest of the app uses to talk to Audible."""

from __future__ import annotations

from typing import Any

from . import content, library, storage
from .auth import LoginFlow, LoginResult
from .content import DownloadInfo
from .models import AudibleBook


class AudibleClient:
    def __init__(self, accounts_dir: str):
        self.accounts_dir = accounts_dir
        self.login = LoginFlow(accounts_dir)

    def _client(self, account_id: str):
        return storage.load_client(self.accounts_dir, account_id)

    # Login (blocking network calls: call from a worker thread).
    def start_login(self, locale: str, name: str) -> tuple[str, str]:
        return self.login.start(locale, name)

    def complete_login(self, state: str, response_url: str) -> LoginResult:
        return self.login.complete(state, response_url)

    def save_login(self, token_key: str, auth: Any) -> None:
        self.login.save(token_key, auth)

    def remove_login(self, token_key: str) -> None:
        self.login.remove(token_key)

    async def get_library(self, account_id: str) -> list[AudibleBook]:
        return await library.fetch_library(self._client(account_id))

    async def get_download_info(self, account_id: str, asin: str) -> DownloadInfo:
        return await content.get_download_info(self._client(account_id), asin)

    async def get_chapter_info(self, account_id: str, asin: str) -> dict[str, Any]:
        return await content.get_chapter_info(self._client(account_id), asin)

    async def get_pdf(self, account_id: str, asin: str) -> bytes | None:
        return await content.get_pdf(self._client(account_id), asin)
