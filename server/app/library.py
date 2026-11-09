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

            _import_genres(conn, book_id, b.get("genres") or [])

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


def _import_genres(conn, book_id: int, ladders: list[list[dict[str, str]]]) -> None:
    """Store Audible's genre ladders (top-level → most specific) and link the
    book to the most specific genre of each. Replaces the book's genres."""
    conn.execute("DELETE FROM book_categories WHERE book_id = ?", (book_id,))
    for ladder in ladders:
        parent_id = None
        for rung in ladder:
            if not rung.get("id") or not rung.get("name"):
                parent_id = None
                break
            conn.execute(
                "INSERT INTO categories (audible_id, name, parent_id) VALUES (?, ?, ?) "
                "ON CONFLICT(audible_id) DO UPDATE SET name = excluded.name, parent_id = excluded.parent_id",
                (rung["id"], rung["name"], parent_id),
            )
            parent_id = conn.execute("SELECT id FROM categories WHERE audible_id = ?", (rung["id"],)).fetchone()[0]
        if parent_id is not None:
            conn.execute("INSERT OR IGNORE INTO book_categories (book_id, category_id) VALUES (?, ?)",
                         (book_id, parent_id))


def genres(db: Database, book_ids: list[int]) -> dict[int, list[str]]:
    """Most specific genre names per book, in the order Audible lists them."""
    out: dict[int, list[str]] = {i: [] for i in book_ids}
    if not book_ids:
        return out
    marks = ",".join("?" * len(book_ids))
    for r in db.query(
        f"""SELECT bc.book_id, c.name FROM book_categories bc JOIN categories c ON c.id = bc.category_id
            WHERE bc.book_id IN ({marks}) ORDER BY bc.rowid""",
        book_ids,
    ):
        if r["name"] not in out[r["book_id"]]:
            out[r["book_id"]].append(r["name"])
    return out


def _contributors_for(db: Database, book_ids: list[int]) -> dict[int, dict[str, list[str]]]:
    out: dict[int, dict[str, list[str]]] = {i: {"author": [], "narrator": []} for i in book_ids}
    if not book_ids:
        return out
    marks = ",".join("?" * len(book_ids))
    for r in db.query(
        f"""SELECT bc.book_id, bc.role, c.name FROM book_contributors bc
            JOIN contributors c ON c.id = bc.contributor_id
            WHERE bc.book_id IN ({marks}) ORDER BY bc.role, bc.sort_order, bc.rowid""",
        book_ids,
    ):
        out[r["book_id"]].setdefault(r["role"], []).append(r["name"])
    return out


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


MAX_PAGE_SIZE = 500

_SUMMARY_COLUMNS = """b.id, b.audible_id, b.title, COALESCE(b.cover_url, '') AS cover_url,
    lb.liberation_status, lb.is_finished, lb.is_deleted, lb.is_hidden, lb.tags, lb.account_id,
    lb.last_format, b.length_minutes, lb.date_added"""


def list_books(db: Database, *, search: str = "", sort: str | None = None, order: str | None = None,
               page: int = 1, limit: int = PAGE_SIZE, account_id: int | None = None) -> list[dict[str, Any]]:
    clause = order_by(sort, order)
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    offset = (max(page, 1) - 1) * limit
    where, params = [], []
    if account_id is not None:
        where.append("lb.account_id = ?")
        params.append(account_id)
    match = fts_query(search) if search else ""
    if search and not match:
        return []  # nothing searchable in the text (e.g. only punctuation)
    if match:
        where.append("books_fts MATCH ?")
        params.append(match)
        joins = "JOIN books_fts f ON f.rowid = b.id"
        # Without an explicit sort, search results stay in relevance order.
        ordering = clause if sort else "rank"
    else:
        joins = ""
        ordering = f"lb.is_deleted ASC, {clause}"
    rows = db.query(
        f"""SELECT {_SUMMARY_COLUMNS} FROM books b
            JOIN library_books lb ON lb.book_id = b.id {joins}
            {"WHERE " + " AND ".join(where) if where else ""}
            ORDER BY {ordering}
            LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )
    ids = [r["id"] for r in rows]
    people, genre_names = _contributors_for(db, ids), genres(db, ids)
    return [
        {
            **dict(r),
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
    r = db.query_one(
        """SELECT b.id, b.audible_id, b.title, COALESCE(b.subtitle,'') AS subtitle,
                  COALESCE(b.description,'') AS description, COALESCE(b.cover_url,'') AS cover_url,
                  b.length_minutes, COALESCE(b.publisher,'') AS publisher,
                  COALESCE(b.language,'') AS language, COALESCE(b.audible_rating,0) AS audible_rating,
                  lb.liberation_status, lb.is_finished, lb.tags, lb.user_rating, lb.account_id,
                  lb.is_hidden, lb.last_format, lb.file_path
           FROM books b JOIN library_books lb ON lb.book_id = b.id
           WHERE b.id = ?""",
        (book_id,),
    )
    if r is None:
        return None
    book = {**dict(r), "is_finished": bool(r["is_finished"]), "is_hidden": bool(r["is_hidden"]),
            "audible_rating": round(r["audible_rating"], 2), "genres": genres(db, [book_id])[book_id]}
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


def update_book(db: Database, book_id: int, *, tags: str | None = None, user_rating: float | None = None,
                is_finished: bool | None = None, is_hidden: bool | None = None) -> None:
    if is_hidden is not None:
        set_hidden(db, [book_id], is_hidden)
    if tags is not None:
        db.execute("UPDATE library_books SET tags = ? WHERE book_id = ?", (tags, book_id))
    if user_rating is not None:
        db.execute("UPDATE library_books SET user_rating = ? WHERE book_id = ?", (user_rating, book_id))
    if is_finished is not None:
        db.execute("UPDATE library_books SET is_finished = ? WHERE book_id = ?", (int(is_finished), book_id))


def set_hidden(db: Database, book_ids: list[int], hidden: bool) -> None:
    if not book_ids:
        return
    marks = ",".join("?" * len(book_ids))
    db.execute(f"UPDATE library_books SET is_hidden = ? WHERE book_id IN ({marks})", (int(hidden), *book_ids))


def book_meta(db: Database, book_id: int, account_id: int | None = None) -> dict | None:
    """What a download needs to know about a book: its account and the values
    the filename/folder templates use. account_id defaults to the book's own."""
    row = db.query_one(
        """SELECT a.audible_account_id, a.id AS account_id, b.audible_id, b.title, COALESCE(b.language,'') AS language,
                  COALESCE(b.length_minutes,0) AS length_minutes, COALESCE(lb.date_added,'') AS date_added,
                  COALESCE(b.date_published,'') AS date_published
           FROM accounts a
           JOIN library_books lb ON lb.account_id = a.id
           JOIN books b ON b.id = lb.book_id
           WHERE b.id = ? AND (? IS NULL OR a.id = ?)""",
        (book_id, account_id, account_id),
    )
    if row is None:
        return None
    meta = dict(row)
    people = contributors(db, book_id)
    meta["authors"], meta["narrators"] = ", ".join(people["author"]), ", ".join(people["narrator"])
    series = db.query_one(
        """SELECT s.name, COALESCE(sb.book_index,'') AS idx FROM series s
           JOIN series_books sb ON sb.series_id = s.id WHERE sb.book_id = ? LIMIT 1""",
        (book_id,),
    )
    meta["series_name"], meta["series_index"] = (series["name"], series["idx"]) if series else ("", "")
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


# --- download status ---------------------------------------------------------


def mark_downloaded(db: Database, book_id: int, fmt: str, file_path: str | None = None) -> None:
    db.execute(
        "UPDATE library_books SET liberation_status = 'liberated', last_downloaded = CURRENT_TIMESTAMP, "
        "last_format = ?, file_path = COALESCE(?, file_path) WHERE book_id = ?",
        (fmt, file_path, book_id),
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
