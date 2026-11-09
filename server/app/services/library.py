"""The library: importing scans, listing/searching, book details, hiding,
download status, finding files on disk and exporting.

Each function is one unit of work (one transaction); the SQL lives in
repositories.books.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..db import Database
from ..repositories import books as repo
from ..repositories.books import MAX_PAGE_SIZE, PAGE_SIZE, SORTS, InvalidSort, order_by  # noqa: F401 (re-exported)

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(s: str) -> str:
    s = _UNSAFE.sub("_", s).strip()[:200]
    return s or "audiobook"


# --- import -------------------------------------------------------------------------


def import_library(db: Database, account_id: int, books: list[dict[str, Any]]) -> int:
    """Upsert an account's books from an Audible scan.

    Books missing from the scan are marked removed for this account; books
    that reappear are restored. Returns the number of books processed.
    """
    with db.session() as s:
        for b in books:
            book_id = repo.upsert_book(s, b)
            repo.upsert_library_entry(s, book_id, account_id, b.get("date_added") or "1970-01-01",
                                      bool(b.get("is_plus_catalog_item")))
            repo.set_contributors(s, book_id, "author", b.get("authors") or [])
            repo.set_contributors(s, book_id, "narrator", b.get("narrators") or [])
            for series in b.get("series") or []:
                if series.get("asin"):
                    repo.add_series(s, book_id, series["asin"], series.get("title") or "", series.get("sequence") or "")
            repo.replace_genres(s, book_id, b.get("genres") or [])
            repo.index_for_search(
                s, book_id,
                title=b.get("title") or "", subtitle=b.get("subtitle") or "", description=b.get("description") or "",
                authors=", ".join(b.get("authors") or []), narrators=", ".join(b.get("narrators") or []),
                series=", ".join(x.get("title") or "" for x in b.get("series") or []),
            )
        repo.mark_missing_as_removed(s, account_id, [b["asin"] for b in books])
    return len(books)


# --- list / search / detail ---------------------------------------------------------


def fts_query(text: str) -> str:
    """Turn search box text into an FTS5 query: every word, matched as a prefix.

    Quoting each word means punctuation can't break the query syntax.
    """
    words = re.findall(r"\w+", text)
    return " ".join('"' + w.replace('"', '""') + '"*' for w in words)


def list_books(db: Database, *, search: str = "", sort: str | None = None, order: str | None = None,
               page: int = 1, limit: int = PAGE_SIZE, account_id: int | None = None) -> list[dict[str, Any]]:
    """A page of the library. Raises InvalidSort for an unknown sort/order."""
    order_by(sort, order)  # validate even when the search matches nothing
    match = fts_query(search) if search else ""
    if search and not match:
        return []  # nothing searchable in the text (e.g. only punctuation)
    with db.session() as s:
        rows = repo.list_summaries(s, fts_match=match, sort=sort, order=order, page=page, limit=limit,
                                   account_id=account_id)
        ids = [r["id"] for r in rows]
        people, genre_names = repo.contributors(s, ids), repo.genres(s, ids)
    return [
        {
            **r,
            "is_finished": bool(r["is_finished"]),
            "is_deleted": bool(r["is_deleted"]),
            "is_hidden": bool(r["is_hidden"]),
            "authors": people[r["id"]]["author"],
            "narrators": people[r["id"]]["narrator"],
            "genres": genre_names[r["id"]],
        }
        for r in rows
    ]


def get_book(db: Database, book_id: int) -> dict[str, Any] | None:
    with db.session() as s:
        r = repo.get_detail(s, book_id)
        if r is None:
            return None
        people = repo.contributors(s, [book_id])[book_id]
        book = {
            **r,
            "is_finished": bool(r["is_finished"]),
            "is_hidden": bool(r["is_hidden"]),
            "audible_rating": round(r["audible_rating"], 2),
            "genres": repo.genres(s, [book_id])[book_id],
            "authors": people["author"],
            "narrators": people["narrator"],
            "series": [{"name": x["name"], "index": x["idx"]} for x in repo.series_of(s, book_id)],
        }
    return book


def contributors(db: Database, book_id: int) -> dict[str, list[str]]:
    with db.session() as s:
        return repo.contributors(s, [book_id])[book_id]


def genres(db: Database, book_ids: list[int]) -> dict[int, list[str]]:
    with db.session() as s:
        return repo.genres(s, book_ids)


def update_book(db: Database, book_id: int, *, tags: str | None = None, user_rating: float | None = None,
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
        with db.session() as s:
            repo.update_fields(s, book_id, **fields)


def set_hidden(db: Database, book_ids: list[int], hidden: bool) -> None:
    with db.session() as s:
        repo.set_hidden(s, book_ids, hidden)


# --- naming (what a download is called) ------------------------------------------------


def book_meta(db: Database, book_id: int, account_id: int | None = None) -> dict | None:
    """What a download needs to know about a book: its account and the values
    the filename/folder templates use. account_id defaults to the book's own."""
    with db.session() as s:
        row = repo.download_meta(s, book_id, account_id)
        if row is None:
            return None
        people = repo.contributors(s, [book_id])[book_id]
        series = repo.series_of(s, book_id)
    meta = dict(row)
    meta["authors"], meta["narrators"] = ", ".join(people["author"]), ", ".join(people["narrator"])
    meta["series_name"], meta["series_index"] = (series[0]["name"], series[0]["idx"]) if series else ("", "")
    return meta


def naming_data(meta: dict) -> dict[str, str]:
    """Template values (see jobs.filename.FilenameData) from book_meta()."""
    # {year} is the publication year; fall back to when it joined the library.
    year = (meta["date_published"] or meta["date_added"])[:4]
    minutes = meta["length_minutes"]
    return {
        "title": meta["title"],
        "authors": meta["authors"],
        "narrators": meta["narrators"],
        "series_name": meta["series_name"],
        "series_index": meta["series_index"],
        "year": year if len(year) == 4 else "",
        "language": meta["language"],
        "duration_h": str(minutes // 60) if minutes > 0 else "",
    }


def planned_path(db: Database, book_id: int, config) -> str:
    """Where a download of this book would be saved with the current settings."""
    from ..jobs.filename import FilenameData, book_directory, render_filename

    meta = book_meta(db, book_id)
    if meta is None:
        return ""
    names = FilenameData(**naming_data(meta))
    folder = book_directory(config.output_dir, config.folder_template, names)
    return os.path.join(folder, f"{render_filename(config.filename_template, names)}.{config.default_format}")


# --- download status ---------------------------------------------------------------------


def mark_downloaded(db: Database, book_id: int, fmt: str, file_path: str | None = None) -> None:
    with db.session() as s:
        repo.mark_downloaded(s, book_id, fmt, file_path)


def mark_error(db: Database, book_id: int) -> None:
    with db.session() as s:
        repo.mark_error(s, book_id)


# --- find downloaded files ------------------------------------------------------------------


def audio_files_on_disk(root: str) -> dict[str, str]:
    """Basename (no extension) → format, for every .m4b/.mp3 under root,
    including inside per-book folders. Hidden directories are skipped."""
    found: dict[str, str] = {}
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            p = Path(name)
            ext = p.suffix.lower()
            if ext in (".m4b", ".mp3"):
                found[p.stem] = ext[1:]
    return found


def rescan(db: Database, output_dir: str) -> int:
    """Mark books whose audio file is on disk as downloaded. Returns matches."""
    on_disk = audio_files_on_disk(output_dir)
    if not on_disk:
        return 0
    with db.session() as s:
        matches = [(r["id"], on_disk[sanitize_filename(r["title"])]) for r in repo.not_downloaded_titles(s)
                   if sanitize_filename(r["title"]) in on_disk]
        for book_id, fmt in matches:
            repo.mark_downloaded(s, book_id, fmt)
    return len(matches)


# --- export ------------------------------------------------------------------------------------

EXPORT_FIELDS = [
    "audible_id", "title", "authors", "narrators", "series", "length_minutes", "publisher",
    "language", "audible_rating", "liberation_status", "is_finished", "tags", "user_rating", "date_added",
]


def export_rows(db: Database) -> list[dict[str, Any]]:
    with db.session() as s:
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
            "liberation_status": r["liberation_status"],
            "is_finished": bool(r["is_finished"]),
            "tags": r["tags"],
            "user_rating": None if r["user_rating"] is None else int(r["user_rating"]),
            "date_added": r["date_added"],
        }
        for r in rows
    ]
