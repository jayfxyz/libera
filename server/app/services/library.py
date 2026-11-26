"""The library: importing scans, listing/searching, book details, hiding,
download status, finding files on disk and exporting.

LibraryService's methods are each one unit of work (one transaction); the
SQL lives in repositories.books. The pure helpers below need no database.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, NamedTuple

from ..audible_api.models import AudibleBook
from ..config import Config
from ..db import Database, iso_utc
from ..events import EventBus
from ..jobs.filename import FilenameData, book_directory, book_file_name
from ..naming import legacy_file_name, sanitize_filename
from ..repositories import books as repo
from ..repositories.books import MAX_PAGE_SIZE, PAGE_SIZE, SORTS, InvalidSort, order_by  # noqa: F401 (re-exported)

_ASIN_SUFFIX = re.compile(r" \[([^\[\]]+)\]$")  # the " [B002UZMLXM]" a file or folder name ends with

EXPORT_FIELDS = [
    "audible_id", "title", "authors", "narrators", "series", "length_minutes", "publisher",
    "language", "audible_rating", "download_status", "is_finished", "tags", "user_rating", "date_added",
]


class LibraryService:
    def __init__(self, db: Database, config: Config, events: EventBus):
        self._db = db
        self._config = config
        self._events = events

    # --- import -------------------------------------------------------------------------

    def import_library(self, account_id: int, books: list[AudibleBook]) -> int:
        """Upsert an account's books from an Audible scan.

        Books missing from the scan are marked removed for this account; books
        that reappear are restored. Returns the number of books processed.
        """
        with self._db.session() as s:
            for b in books:
                book_id = repo.upsert_book(s, b)
                repo.upsert_library_entry(s, book_id, account_id, b.date_added or "1970-01-01",
                                          b.is_plus_catalog_item, b.is_downloadable)
                repo.set_contributors(s, book_id, "author", b.authors)
                repo.set_contributors(s, book_id, "narrator", b.narrators)
                for series in b.series:
                    if series.asin:
                        repo.add_series(s, book_id, series.asin, series.title, series.sequence)
                repo.replace_genres(s, book_id, b.genres)
                repo.index_for_search(
                    s, book_id,
                    title=b.title, subtitle=b.subtitle or "", description=b.description or "",
                    authors=", ".join(b.authors), narrators=", ".join(b.narrators),
                    series=", ".join(x.title for x in b.series),
                )
            repo.mark_missing_as_removed(s, account_id, [b.asin for b in books])
        return len(books)

    # --- list / search / detail ---------------------------------------------------------

    def list_books(self, *, search: str = "", sort: str | None = None, order: str | None = None,
                   page: int = 1, limit: int = PAGE_SIZE, account_id: int | None = None) -> list[dict[str, Any]]:
        """A page of the library. Raises InvalidSort for an unknown sort/order."""
        order_by(sort, order)  # validate even when the search matches nothing
        match = fts_query(search) if search else ""
        if search and not match:
            return []  # nothing searchable in the text (e.g. only punctuation)
        with self._db.session() as s:
            rows = repo.list_summaries(s, fts_match=match, sort=sort, order=order, page=page, limit=limit,
                                       account_id=account_id)
            ids = [r["id"] for r in rows]
            people, genre_names = repo.contributors(s, ids), repo.genres(s, ids)
        return [_summary(r, people[r["id"]], genre_names[r["id"]]) for r in rows]

    def book_summary(self, book_id: int) -> dict[str, Any] | None:
        """One book as list_books shows it (the data of a book.updated event)."""
        with self._db.session() as s:
            r = repo.get_summary(s, book_id)
            if r is None:
                return None
            return _summary(r, repo.contributors(s, [book_id])[book_id], repo.genres(s, [book_id])[book_id])

    def publish_book(self, book_id: int) -> None:
        """Announce a book's new download state to open event streams."""
        if (summary := self.book_summary(book_id)) is not None:
            self._events.publish("book.updated", book_id, summary)

    def get_book(self, book_id: int) -> dict[str, Any] | None:
        with self._db.session() as s:
            r = repo.get_detail(s, book_id)
            if r is None:
                return None
            people = repo.contributors(s, [book_id])[book_id]
            book = {
                **r,
                "is_finished": bool(r["is_finished"]),
                "is_hidden": bool(r["is_hidden"]),
                "is_downloadable": bool(r["is_downloadable"]),
                "has_pdf": _has_pdf(r["has_pdf"]),
                "updated_at": iso_utc(r["updated_at"]),
                "audible_rating": round(r["audible_rating"], 2),
                "genres": repo.genres(s, [book_id])[book_id],
                "authors": people["author"],
                "narrators": people["narrator"],
                "series": [{"name": x["name"], "index": x["idx"]} for x in repo.series_of(s, book_id)],
            }
        return book

    def contributors(self, book_id: int) -> dict[str, list[str]]:
        with self._db.session() as s:
            return repo.contributors(s, [book_id])[book_id]

    def genres(self, book_ids: list[int]) -> dict[int, list[str]]:
        with self._db.session() as s:
            return repo.genres(s, book_ids)

    def update_book(self, book_id: int, *, tags: str | None = None, user_rating: float | None = None,
                    is_finished: bool | None = None, is_hidden: bool | None = None) -> None:
        fields: dict[str, Any] = {}
        if tags is not None:
            fields["tags"] = tags
        if user_rating is not None:
            fields["user_rating"] = user_rating
        if is_finished is not None:
            fields["is_finished"] = int(is_finished)
        if is_hidden is not None:
            fields["is_hidden"] = int(is_hidden)
        if fields:
            with self._db.session() as s:
                repo.update_fields(s, book_id, **fields)

    def set_hidden(self, book_ids: list[int], hidden: bool) -> None:
        with self._db.session() as s:
            repo.set_hidden(s, book_ids, hidden)

    # --- naming (what a download is called) ------------------------------------------------

    def book_meta(self, book_id: int, account_id: int | None = None) -> dict | None:
        """What a download needs to know about a book: its account and the values
        the filename/folder templates use. account_id defaults to the book's own."""
        with self._db.session() as s:
            row = repo.download_meta(s, book_id, account_id)
            if row is None:
                return None
            people = repo.contributors(s, [book_id])[book_id]
            series = repo.series_of(s, book_id)
        meta = dict(row)
        meta["authors"], meta["narrators"] = ", ".join(people["author"]), ", ".join(people["narrator"])
        meta["first_author"] = people["author"][0] if people["author"] else ""
        meta["series_name"], meta["series_index"] = (series[0]["name"], series[0]["idx"]) if series else ("", "")
        return meta

    def planned_path(self, book_id: int) -> str:
        """Where this book's file is, or where a download of it would be saved with the current settings."""
        meta = self.book_meta(book_id)
        if meta is None:
            return ""
        if meta["file_path"]:
            return meta["file_path"]
        c = self._config
        names = FilenameData(**naming_data(meta))
        folder = book_directory(c.output_dir, c.naming, names)
        return os.path.join(folder, f"{book_file_name(names)}.{c.default_format}")

    # --- download status ---------------------------------------------------------------------

    def mark_downloaded(self, book_id: int, fmt: str, file_path: str | None = None) -> None:
        with self._db.session() as s:
            repo.mark_downloaded(s, book_id, fmt, file_path)
        self.publish_book(book_id)

    def mark_error(self, book_id: int) -> None:
        with self._db.session() as s:
            repo.mark_error(s, book_id)
        self.publish_book(book_id)

    # --- find downloaded files ------------------------------------------------------------------

    def rescan(self) -> int:
        """Mark books whose audio file is in the output folder as downloaded. Returns matches."""
        on_disk = audio_files_on_disk(self._config.output_dir)
        if not on_disk:
            return 0
        by_asin = asin_files_on_disk(on_disk)
        with self._db.session() as s:
            matches = [(r["id"], file) for r in repo.not_downloaded_books(s)
                       if (file := by_asin.get(r["audible_id"])
                           or title_file_on_disk(title=r["title"], title_is_unique=r["same_title"] == 1,
                                                 on_disk=on_disk))]
            for book_id, file in matches:
                repo.mark_downloaded(s, book_id, file.format, file.path)
        for book_id, _ in matches:
            self.publish_book(book_id)
        return len(matches)

    # --- export ------------------------------------------------------------------------------------

    def export_rows(self) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = repo.export_rows(s)
            ids = [r["id"] for r in rows]
            people, series = repo.contributors(s, ids), repo.series_names(s, ids)
        return [
            {
                "audible_id": r["audible_id"],
                "title": r["title"],
                "authors": ", ".join(people[r["id"]]["author"]),
                "narrators": ", ".join(people[r["id"]]["narrator"]),
                "series": ", ".join(series[r["id"]]),
                "length_minutes": r["length_minutes"],
                "publisher": r["publisher"],
                "language": r["language"],
                "audible_rating": round(r["audible_rating"], 2),
                "download_status": r["download_status"],
                "is_finished": bool(r["is_finished"]),
                "tags": r["tags"],
                "user_rating": None if r["user_rating"] is None else int(r["user_rating"]),
                "date_added": r["date_added"],
            }
            for r in rows
        ]


# --- pure helpers (no database) ---------------------------------------------------------------

class DiskFile(NamedTuple):
    """An audio file found in the output folder."""

    format: str
    path: str


def asin_files_on_disk(on_disk: dict[str, DiskFile]) -> dict[str, DiskFile]:
    """ASIN → file, for the files in on_disk named "<title> [<asin>]"."""
    return {match.group(1): file for stem, file in on_disk.items() if (match := _ASIN_SUFFIX.search(stem))}


def title_file_on_disk(title: str, title_is_unique: bool, on_disk: dict[str, DiskFile]) -> DiskFile | None:
    """The book's audio file in on_disk, named after the title alone (or, before November 2026, with ":"
    as "_", e.g. "Found_ Book"). It counts only when no other book has that title: it could be any of them."""
    if not title_is_unique:
        return None
    for name in (sanitize_filename(title), legacy_file_name(title)):
        if name in on_disk:
            return on_disk[name]
    return None


def fts_query(text: str) -> str:
    """Turn search box text into an FTS5 query: every word, matched as a prefix.

    Quoting each word means punctuation can't break the query syntax.
    """
    words = re.findall(r"\w+", text)
    return " ".join('"' + w.replace('"', '""') + '"*' for w in words)


def naming_data(meta: dict) -> dict[str, str]:
    """Template values (see jobs.filename.FilenameData) from LibraryService.book_meta()."""
    # {year} is the publication year; fall back to when it joined the library.
    year = (meta["date_published"] or meta["date_added"])[:4]
    return {
        "title": meta["title"],
        "author": meta["first_author"],
        "series_name": meta["series_name"],
        "series_index": meta["series_index"],
        "year": year if len(year) == 4 else "",
        "asin": meta["audible_id"],
    }


def audio_files_on_disk(root: str) -> dict[str, DiskFile]:
    """Basename (no extension) → file, for every .m4b/.mp3 under root,
    including inside per-book folders. Hidden directories are skipped."""
    found: dict[str, DiskFile] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            p = Path(name)
            ext = p.suffix.lower()
            if ext in (".m4b", ".mp3"):
                found[p.stem] = DiskFile(format=ext[1:], path=os.path.join(dirpath, name))
    return found


def _summary(r: dict[str, Any], people: dict[str, list[str]], genre_names: list[str]) -> dict[str, Any]:
    """A library list row as the API returns it."""
    return {
        **r,
        "is_finished": bool(r["is_finished"]),
        "is_deleted": bool(r["is_deleted"]),
        "is_hidden": bool(r["is_hidden"]),
        "is_downloadable": bool(r["is_downloadable"]),
        "has_pdf": _has_pdf(r["has_pdf"]),
        "updated_at": iso_utc(r["updated_at"]),
        "account_ids": sorted(int(i) for i in r["account_ids"].split(",")) if r["account_ids"] else [],
        "authors": people["author"],
        "narrators": people["narrator"],
        "genres": genre_names,
    }


def _has_pdf(value: int | None) -> bool | None:
    """None: not synced since the flag existed."""
    return None if value is None else bool(value)
