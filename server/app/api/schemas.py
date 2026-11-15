"""Request bodies of the API."""

from __future__ import annotations

from pydantic import BaseModel

# --- accounts -------------------------------------------------------------------------


class AccountPatch(BaseModel):
    account_name: str | None = None


class AuthStart(BaseModel):
    locale: str = ""
    name: str = ""


class AuthComplete(BaseModel):
    state: str = ""
    response_url: str = ""


# --- library --------------------------------------------------------------------------


class BulkUpdate(BaseModel):
    book_ids: list[int]
    is_hidden: bool


class BookPatch(BaseModel):
    tags: str | None = None
    user_rating: float | None = None
    is_finished: bool | None = None
    is_hidden: bool | None = None


# --- downloads ------------------------------------------------------------------------


class DownloadOptions(BaseModel):
    format: str = ""  # m4b/mp3; "" = the default from Settings
    split_chapters: bool = False


class EnqueueRequest(DownloadOptions):
    book_id: int
    audible_id: str = ""  # accepted for older clients; the book's own ASIN is used
    account_id: int | None = None


class BulkEnqueueRequest(DownloadOptions):
    book_ids: list[int]


# --- settings -------------------------------------------------------------------------


class SettingsPatch(BaseModel):
    # Unknown fields (the UI sends the whole settings object back) are ignored.
    output_dir: str | None = None
    download_workers: int | None = None
    default_format: str | None = None
    filename_template: str | None = None
    folder_template: str | None = None
