"""Request bodies of the API, and the responses that are not plain dicts."""

from __future__ import annotations

from pydantic import BaseModel

from ..config import NamingPreset
from ..services.book_files import FileKind

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


# --- a book's files on disk ------------------------------------------------------------


class BookFile(BaseModel):
    name: str
    size_bytes: int
    kind: FileKind


class BookFiles(BaseModel):
    root: str  # the output folder (or, for a book outside it, the folder above the book's)
    folders: list[str]  # from root down to the book's own folder
    files: list[BookFile]
    found: bool  # False when the book has no file on disk


# --- moving downloaded books ----------------------------------------------------------


class MoveRequest(BaseModel):
    naming: NamingPreset


# --- settings -------------------------------------------------------------------------


class SettingsPatch(BaseModel):
    # Unknown fields (the UI sends the whole settings object back) are ignored.
    download_workers: int | None = None
    default_format: str | None = None
    naming: NamingPreset | None = None
    layout_dialog_seen: bool | None = None
