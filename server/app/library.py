"""Library queries: import from Audible, list/sort/search, detail, rescan, export."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database

PAGE_SIZE = 50

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(s: str) -> str:
    s = _UNSAFE.sub("_", s).strip()[:200]
    return s or "audiobook"


# --- import -----------------------------------------------------------------


def import_library(db: Database, account_id: int, books: list[dict[str, Any]]) -> int:
    """Upsert an account's books from an Audible scan.

    Books missing from the scan are marked is_deleted=1 for this account;
    books that reappear are restored. Returns the number of books processed.
    """
    with db.transaction() as conn:
        for b in books:
            conn.execute(
                """
                INSERT INTO books (audible_id, title, subtitle, description, length_minutes, locale,
                                   cover_url, publisher, audible_rating, language, date_published)
                VALUES (?, ?, ?, ?, ?, '', ?, ?, ?, NULLIF(?, ''), NULLIF(?, ''))
                ON CONFLICT(audible_id) DO UPDATE SET
                    title = excluded.title,
                    cover_url = excluded.cover_url,
                    audible_rating = excluded.audible_rating,
                    language = COALESCE(excluded.language, books.language),
                    date_published = COALESCE(excluded.date_published, books.date_published)
                """,
                (
                    b["asin"], b.get("title") or "", b.get("subtitle"), b.get("description"),
                    b.get("runtime_length_min") or 0, b.get("cover_url"), b.get("publisher_name"),
                    b.get("rating"), b.get("language") or "", b.get("release_date") or "",
                ),
            )
            book_id = conn.execute("SELECT id FROM books WHERE audible_id = ?", (b["asin"],)).fetchone()[0]

            conn.execute(
                """
                INSERT INTO library_books (book_id, account_id, date_added, is_audible_plus, is_deleted)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(book_id, account_id) DO UPDATE SET
                    date_added = excluded.date_added,
                    is_deleted = 0
                """,
                (book_id, account_id, b.get("date_added") or "1970-01-01", int(bool(b.get("is_plus_catalog_item")))),
            )

            for role, names in (("author", b.get("authors") or []), ("narrator", b.get("narrators") or [])):
                for order, name in enumerate(names):
                    conn.execute("INSERT INTO contributors (name) VALUES (?) ON CONFLICT(name) DO NOTHING", (name,))
                    cid = conn.execute("SELECT id FROM contributors WHERE name = ?", (name,)).fetchone()[0]
                    conn.execute(
                        """
                        INSERT INTO book_contributors (book_id, contributor_id, role, sort_order)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(book_id, contributor_id, role) DO UPDATE SET sort_order = excluded.sort_order
                        """,
                        (book_id, cid, role, order),
                    )

            for s in b.get("series") or []:
                if not s.get("asin"):
                    continue
                conn.execute(
                    "INSERT INTO series (audible_id, name) VALUES (?, ?) "
                    "ON CONFLICT(audible_id) DO UPDATE SET name = excluded.name",
                    (s["asin"], s.get("title") or ""),
                )
                sid = conn.execute("SELECT id FROM series WHERE audible_id = ?", (s["asin"],)).fetchone()[0]
                conn.execute(
                    "INSERT OR IGNORE INTO series_books (series_id, book_id, book_index) VALUES (?, ?, ?)",
                    (sid, book_id, s.get("sequence") or ""),
                )

            # Contentless FTS table: no upsert, so delete and re-insert.
            conn.execute("DELETE FROM books_fts WHERE rowid = ?", (book_id,))
            conn.execute(
                "INSERT INTO books_fts (rowid, title, subtitle, description, authors, narrators, series_name, tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '')",
                (
                    book_id, b.get("title") or "", b.get("subtitle") or "", b.get("description") or "",
                    ", ".join(b.get("authors") or []), ", ".join(b.get("narrators") or []),
                    ", ".join(s.get("title") or "" for s in b.get("series") or []),
                ),
            )

        seen = [b["asin"] for b in books]
        if seen:
            marks = ",".join("?" * len(seen))
            conn.execute(
                f"UPDATE library_books SET is_deleted = 1 WHERE account_id = ? "
                f"AND book_id IN (SELECT id FROM books WHERE audible_id NOT IN ({marks}))",
                (account_id, *seen),
            )
        else:
            conn.execute("UPDATE library_books SET is_deleted = 1 WHERE account_id = ?", (account_id,))
    return len(books)


# --- list / sort / search --------------------------------------------------


@dataclass(frozen=True)
class _Sort:
    keys: tuple[str, ...]  # SQL expressions, most significant first
    default_dir: str  # "asc" or "desc": the natural direction


_PRIMARY_AUTHOR = """(SELECT c.name FROM book_contributors bc
    JOIN contributors c ON c.id = bc.contributor_id
    WHERE bc.book_id = b.id AND bc.role = 'author'
    ORDER BY bc.sort_order, bc.rowid LIMIT 1)"""
_SERIES_NAME = """(SELECT s.name FROM series_books sb JOIN series s ON s.id = sb.series_id
    WHERE sb.book_id = b.id ORDER BY sb.rowid LIMIT 1)"""
_SERIES_INDEX = """(SELECT CAST(NULLIF(sb.book_index, '') AS REAL) FROM series_books sb
    WHERE sb.book_id = b.id ORDER BY sb.rowid LIMIT 1)"""

# Fixed SQL only: nothing user-supplied reaches ORDER BY.
SORTS: dict[str, _Sort] = {
    "title": _Sort(("b.title COLLATE NOCASE",), "asc"),
    "author": _Sort((_PRIMARY_AUTHOR + " COLLATE NOCASE",), "asc"),
    "added": _Sort(("lb.date_added",), "desc"),
    "released": _Sort(("NULLIF(b.date_published, '')",), "desc"),
    "length": _Sort(("b.length_minutes",), "desc"),
    "series": _Sort((_SERIES_NAME + " COLLATE NOCASE", _SERIES_INDEX), "asc"),
    "rating": _Sort(("NULLIF(b.audible_rating, 0)",), "desc"),
    "downloaded": _Sort(("lb.last_downloaded",), "desc"),
}


class InvalidSort(ValueError):
    pass


def order_by(sort: str | None, order: str | None) -> str:
    """ORDER BY list for a sort name and direction.

    Empty sort means title; empty order means the sort's natural direction.
    Books missing the sorted value always come last; ties fall back to title.
    """
    name = sort or "title"
    if name not in SORTS:
        raise InvalidSort(f"unknown sort {name!r}")
    if order not in (None, "", "asc", "desc"):
        raise InvalidSort(f"unknown order {order!r}")
    s = SORTS[name]
    direction = (order or s.default_dir).upper()
    parts = [f"{k} {direction} NULLS LAST" for k in s.keys]
    if name != "title":
        parts.append("b.title COLLATE NOCASE ASC")
    parts.append("b.id ASC")
    return ", ".join(parts)


def fts_query(text: str) -> str:
    """Turn search box text into an FTS5 query: every word, matched as a prefix.

    Quoting each word means punctuation can't break the query syntax.
    """
    words = re.findall(r"\w+", text)
    return " ".join('"' + w.replace('"', '""') + '"*' for w in words)


_SUMMARY_COLUMNS = """b.id, b.audible_id, b.title, COALESCE(b.cover_url, '') AS cover_url,
    lb.liberation_status, lb.is_finished, lb.is_deleted, lb.tags, lb.account_id"""


def list_books(db: Database, *, search: str = "", sort: str | None = None,
               order: str | None = None, page: int = 1) -> list[dict[str, Any]]:
    clause = order_by(sort, order)
    offset = (max(page, 1) - 1) * PAGE_SIZE
    match = fts_query(search) if search else ""
    if match:
        # Without an explicit sort, search results stay in relevance order.
        rows = db.query(
            f"""SELECT {_SUMMARY_COLUMNS} FROM books b
                JOIN library_books lb ON lb.book_id = b.id
                JOIN books_fts f ON f.rowid = b.id
                WHERE books_fts MATCH ?
                ORDER BY {clause if sort else "rank"}
                LIMIT ? OFFSET ?""",
            (match, PAGE_SIZE, offset),
        )
    elif search:
        rows = []  # nothing searchable in the text (e.g. only punctuation)
    else:
        rows = db.query(
            f"""SELECT {_SUMMARY_COLUMNS} FROM books b
                JOIN library_books lb ON lb.book_id = b.id
                ORDER BY lb.is_deleted ASC, {clause}
                LIMIT ? OFFSET ?""",
            (PAGE_SIZE, offset),
        )
    return [
        {**dict(r), "is_finished": bool(r["is_finished"]), "is_deleted": bool(r["is_deleted"])}
        for r in rows
    ]


def get_book(db: Database, book_id: int) -> dict[str, Any] | None:
    r = db.query_one(
        """SELECT b.id, b.audible_id, b.title, COALESCE(b.subtitle,'') AS subtitle,
                  COALESCE(b.description,'') AS description, COALESCE(b.cover_url,'') AS cover_url,
                  b.length_minutes, COALESCE(b.publisher,'') AS publisher,
                  COALESCE(b.language,'') AS language, COALESCE(b.audible_rating,0) AS audible_rating,
                  lb.liberation_status, lb.is_finished, lb.tags, lb.user_rating, lb.account_id
           FROM books b JOIN library_books lb ON lb.book_id = b.id
           WHERE b.id = ?""",
        (book_id,),
    )
    if r is None:
        return None
    book = {**dict(r), "is_finished": bool(r["is_finished"]), "audible_rating": round(r["audible_rating"], 2)}
    people = contributors(db, book_id)
    book["authors"], book["narrators"] = people["author"], people["narrator"]
    book["series"] = [
        {"name": s["name"], "index": s["idx"]}
        for s in db.query(
            """SELECT s.name, COALESCE(sb.book_index,'') AS idx FROM series s
               JOIN series_books sb ON sb.series_id = s.id WHERE sb.book_id = ?""",
            (book_id,),
        )
    ]
    return book


def contributors(db: Database, book_id: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"author": [], "narrator": []}
    for r in db.query(
        """SELECT c.name, bc.role FROM contributors c
           JOIN book_contributors bc ON bc.contributor_id = c.id
           WHERE bc.book_id = ? ORDER BY bc.role, bc.sort_order, bc.rowid""",
        (book_id,),
    ):
        out.setdefault(r["role"], []).append(r["name"])
    return out


def update_book(db: Database, book_id: int, *, tags: str | None = None,
                user_rating: float | None = None, is_finished: bool | None = None) -> None:
    if tags is not None:
        db.execute("UPDATE library_books SET tags = ? WHERE book_id = ?", (tags, book_id))
    if user_rating is not None:
        db.execute("UPDATE library_books SET user_rating = ? WHERE book_id = ?", (user_rating, book_id))
    if is_finished is not None:
        db.execute("UPDATE library_books SET is_finished = ? WHERE book_id = ?", (int(is_finished), book_id))


# --- download status ---------------------------------------------------------


def mark_downloaded(db: Database, book_id: int, fmt: str) -> None:
    db.execute(
        "UPDATE library_books SET liberation_status = 'liberated', last_downloaded = CURRENT_TIMESTAMP, "
        "last_format = ? WHERE book_id = ?",
        (fmt, book_id),
    )


def mark_error(db: Database, book_id: int) -> None:
    db.execute(
        "UPDATE library_books SET liberation_status = 'error' "
        "WHERE book_id = ? AND liberation_status != 'liberated'",
        (book_id,),
    )


# --- rescan files on disk -----------------------------------------------------


def audio_files_on_disk(root: str) -> dict[str, str]:
    """Basename (no extension) → format, for every .m4b/.mp3 under root,
    including inside per-book folders. Hidden directories are skipped."""
    found: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
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
    rows = db.query(
        """SELECT b.id, b.title FROM books b JOIN library_books lb ON lb.book_id = b.id
           WHERE lb.liberation_status != 'liberated'"""
    )
    matches = [(r["id"], on_disk[sanitize_filename(r["title"])]) for r in rows
               if sanitize_filename(r["title"]) in on_disk]
    for book_id, fmt in matches:
        mark_downloaded(db, book_id, fmt)
    return len(matches)


# --- export ---------------------------------------------------------------------

EXPORT_FIELDS = [
    "audible_id", "title", "authors", "narrators", "series", "length_minutes", "publisher",
    "language", "audible_rating", "liberation_status", "is_finished", "tags", "user_rating", "date_added",
]


def export_rows(db: Database) -> list[dict[str, Any]]:
    rows = db.query(
        """SELECT b.id, b.audible_id, b.title, COALESCE(b.length_minutes,0) AS length_minutes,
                  COALESCE(b.publisher,'') AS publisher, COALESCE(b.language,'') AS language,
                  COALESCE(b.audible_rating,0) AS audible_rating, lb.liberation_status, lb.is_finished,
                  lb.tags, lb.user_rating, lb.date_added
           FROM books b JOIN library_books lb ON lb.book_id = b.id
           WHERE lb.is_deleted = 0 ORDER BY b.title"""
    )
    out = []
    for r in rows:
        people = contributors(db, r["id"])
        series = db.query(
            "SELECT s.name FROM series s JOIN series_books sb ON sb.series_id = s.id WHERE sb.book_id = ?",
            (r["id"],),
        )
        out.append({
            "audible_id": r["audible_id"],
            "title": r["title"],
            "authors": ", ".join(people["author"]),
            "narrators": ", ".join(people["narrator"]),
            "series": ", ".join(s["name"] for s in series),
            "length_minutes": r["length_minutes"],
            "publisher": r["publisher"],
            "language": r["language"],
            "audible_rating": round(r["audible_rating"], 2),
            "liberation_status": r["liberation_status"],
            "is_finished": bool(r["is_finished"]),
            "tags": r["tags"],
            "user_rating": None if r["user_rating"] is None else int(r["user_rating"]),
            "date_added": r["date_added"],
        })
    return out
