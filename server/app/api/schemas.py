"""Request bodies of the API."""

from __future__ import annotations

from pydantic import BaseModel


class DownloadOptions(BaseModel):
    format: str = ""  # m4b/mp3; "" = the default from Settings
    split_chapters: bool = False


class EnqueueRequest(DownloadOptions):
    book_id: int
    audible_id: str = ""  # accepted for older clients; the book's own ASIN is used
    account_id: int | None = None


class BulkEnqueueRequest(DownloadOptions):
    book_ids: list[int]
