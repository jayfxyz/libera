"""Books and their per-account library entries.

The writes on import and the library listing are SQL: they're upserts across
several tables and a sort/search over a full-text index (books_fts, an FTS5
table SQLAlchemy can't model). Everything here takes a Session; the caller
owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from .tasks import now

if TYPE_CHECKING:
    from ..audible_api.models import AudibleBook, Genre


def _rows(s: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    stmt = text(sql)
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            stmt = stmt.bindparams(bindparam(name, expanding=True))
    return [dict(r) for r in s.execute(stmt, params).mappings()]


def _one(s: Session, sql: str, **params: Any) -> dict[str, Any] | None:
    rows = _rows(s, sql, **params)
    return rows[0] if rows else None


# --- import ---------------------------------------------------------------------


def upsert_book(s: Session, b: AudibleBook) -> int:
    """Insert or update a book from a normalised Audible item; returns its id."""
    s.execute(text("""
        INSERT INTO books (audible_id, title, subtitle, description, length_minutes, locale,
                           cover_url, publisher, audible_rating, language, date_published, has_pdf)
        VALUES (:asin, :title, :subtitle, :description, :length, '', :cover, :publisher, :rating,
                NULLIF(:language, ''), NULLIF(:released, ''), :has_pdf)
        ON CONFLICT(audible_id) DO UPDATE SET
            title = excluded.title,
            cover_url = excluded.cover_url,
            audible_rating = excluded.audible_rating,
            language = COALESCE(excluded.language, books.language),
            date_published = COALESCE(excluded.date_published, books.date_published),
            has_pdf = COALESCE(excluded.has_pdf, books.has_pdf)
    """), {
        "asin": b.asin, "title": b.title, "subtitle": b.subtitle, "description": b.description,
        "length": b.runtime_length_min, "cover": b.cover_url, "publisher": b.publisher_name, "rating": b.rating,
        "language": b.language or "", "released": b.release_date or "",
        "has_pdf": b.has_pdf,  # None (not in the scan) keeps what we knew
    })
    return s.execute(text("SELECT id FROM books WHERE audible_id = :asin"), {"asin": b.asin}).scalar_one()


def upsert_library_entry(s: Session, book_id: int, account_id: int, date_added: str, is_plus: bool,
                         is_downloadable: bool = True) -> None:
    """Link a book to an account's library (restoring it if it had been removed)."""
    s.execute(text("""
        INSERT INTO library_books (book_id, account_id, date_added, is_audible_plus, is_downloadable, is_deleted, updated_at)
        VALUES (:book, :account, :added, :plus, :downloadable, 0, :now)
        ON CONFLICT(book_id, account_id) DO UPDATE SET date_added = excluded.date_added,
            is_audible_plus = excluded.is_audible_plus, is_downloadable = excluded.is_downloadable,
            is_deleted = 0, updated_at = excluded.updated_at
    """), {"book": book_id, "account": account_id, "added": date_added, "plus": int(is_plus),
           "downloadable": int(is_downloadable), "now": now()})


def set_contributors(s: Session, book_id: int, role: str, names: list[str]) -> None:
    for order, name in enumerate(names):
        s.execute(text("INSERT INTO contributors (name) VALUES (:name) ON CONFLICT(name) DO NOTHING"), {"name": name})
        cid = s.execute(text("SELECT id FROM contributors WHERE name = :name"), {"name": name}).scalar_one()
        s.execute(text("""
            INSERT INTO book_contributors (book_id, contributor_id, role, sort_order)
            VALUES (:book, :cid, :role, :order)
            ON CONFLICT(book_id, contributor_id, role) DO UPDATE SET sort_order = excluded.sort_order
        """), {"book": book_id, "cid": cid, "role": role, "order": order})


def add_series(s: Session, book_id: int, series_asin: str, name: str, index: str) -> None:
    s.execute(text("""
        INSERT INTO series (audible_id, name) VALUES (:asin, :name)
        ON CONFLICT(audible_id) DO UPDATE SET name = excluded.name
    """), {"asin": series_asin, "name": name})
    sid = s.execute(text("SELECT id FROM series WHERE audible_id = :asin"), {"asin": series_asin}).scalar_one()
    s.execute(text("INSERT OR IGNORE INTO series_books (series_id, book_id, book_index) VALUES (:sid, :book, :idx)"),
              {"sid": sid, "book": book_id, "idx": index})


def replace_genres(s: Session, book_id: int, ladders: list[list[Genre]]) -> None:
    """Store Audible's genre ladders (top-level → most specific) as a tree and link
    the book to the most specific genre of each. Replaces the book's genres."""
    s.execute(text("DELETE FROM book_categories WHERE book_id = :book"), {"book": book_id})
    for ladder in ladders:
        parent_id = None
        for rung in ladder:
            if not rung.id or not rung.name:
                parent_id = None
                break
            s.execute(text("""
                INSERT INTO categories (audible_id, name, parent_id) VALUES (:id, :name, :parent)
                ON CONFLICT(audible_id) DO UPDATE SET name = excluded.name, parent_id = excluded.parent_id
            """), {"id": rung.id, "name": rung.name, "parent": parent_id})
            parent_id = s.execute(text("SELECT id FROM categories WHERE audible_id = :id"), {"id": rung.id}).scalar_one()
        if parent_id is not None:
            s.execute(text("INSERT OR IGNORE INTO book_categories (book_id, category_id) VALUES (:book, :cat)"),
                      {"book": book_id, "cat": parent_id})


def index_for_search(s: Session, book_id: int, *, title: str, subtitle: str, description: str,
                     authors: str, narrators: str, series: str) -> None:
    # Contentless FTS table: no upsert, so delete and re-insert.
    s.execute(text("DELETE FROM books_fts WHERE rowid = :id"), {"id": book_id})
    s.execute(text("""
        INSERT INTO books_fts (rowid, title, subtitle, description, authors, narrators, series_name, tags)
        VALUES (:id, :title, :subtitle, :description, :authors, :narrators, :series, '')
    """), {"id": book_id, "title": title, "subtitle": subtitle, "description": description,
           "authors": authors, "narrators": narrators, "series": series})


def mark_missing_as_removed(s: Session, account_id: int, present_asins: list[str]) -> None:
    """Flag an account's books that the latest scan didn't return."""
    if present_asins:
        _rows_exec(s, """
            UPDATE library_books SET is_deleted = 1, updated_at = :now WHERE account_id = :account
            AND is_deleted = 0 AND book_id IN (SELECT id FROM books WHERE audible_id NOT IN :asins)
        """, account=account_id, asins=present_asins, now=now())
    else:
        s.execute(text("UPDATE library_books SET is_deleted = 1, updated_at = :now WHERE account_id = :account "
                       "AND is_deleted = 0"), {"account": account_id, "now": now()})


def _rows_exec(s: Session, sql: str, **params: Any) -> None:
    stmt = text(sql)
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            stmt = stmt.bindparams(bindparam(name, expanding=True))
    s.execute(stmt, params)


# --- listing ----------------------------------------------------------------------

PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


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
    spec = SORTS[name]
    direction = (order or spec.default_dir).upper()
    parts = [f"{k} {direction} NULLS LAST" for k in spec.keys]
    if name != "title":
        parts.append("b.title COLLATE NOCASE ASC")
    parts.append("b.id ASC")
    return ", ".join(parts)


# account_ids: every account that owns the book, as "3,6" (the service makes it a list).
_SUMMARY_COLUMNS = """b.id, b.audible_id, b.title, COALESCE(b.cover_url, '') AS cover_url,
    lb.download_status, lb.is_finished, lb.is_deleted, lb.is_hidden, lb.is_downloadable,
    lb.tags, lb.account_id,
    (SELECT group_concat(o.account_id) FROM library_books o WHERE o.book_id = b.id) AS account_ids,
    lb.last_format, b.length_minutes, lb.date_added, b.has_pdf, lb.updated_at"""

# The library entry that stands for a book owned by several accounts: one that isn't
# removed, prefers a downloadable copy, then the oldest. get_summary picks the same one.
_REPRESENTATIVE_ENTRY = """lb.id = (SELECT e.id FROM library_books e WHERE e.book_id = b.id
    ORDER BY e.is_deleted, e.is_downloadable DESC, e.id LIMIT 1)"""


def list_summaries(s: Session, *, fts_match: str = "", sort: str | None = None, order: str | None = None,
                   page: int = 1, limit: int = PAGE_SIZE, account_id: int | None = None) -> list[dict[str, Any]]:
    """One page of library rows: one per book, or one per entry of the given account.
    fts_match is an FTS5 query (see services); without an explicit sort, search results
    come in relevance order."""
    clause = order_by(sort, order)
    limit = min(max(limit, 1), MAX_PAGE_SIZE)
    where, params = [], {"limit": limit, "offset": (max(page, 1) - 1) * limit}
    if account_id is not None:
        where.append("lb.account_id = :account")
        params["account"] = account_id
    else:
        where.append(_REPRESENTATIVE_ENTRY)
    if fts_match:
        where.append("books_fts MATCH :match")
        params["match"] = fts_match
        joins, ordering = "JOIN books_fts f ON f.rowid = b.id", clause if sort else "rank"
    else:
        joins, ordering = "", f"lb.is_deleted ASC, {clause}"
    return _rows(s, f"""
        SELECT {_SUMMARY_COLUMNS} FROM books b
        JOIN library_books lb ON lb.book_id = b.id {joins}
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY {ordering}
        LIMIT :limit OFFSET :offset""", **params)


def get_summary(s: Session, book_id: int) -> dict[str, Any] | None:
    """One book as the library list shows it."""
    return _one(s, f"""
        SELECT {_SUMMARY_COLUMNS} FROM books b JOIN library_books lb ON lb.book_id = b.id
        WHERE b.id = :id ORDER BY lb.is_deleted, lb.is_downloadable DESC, lb.id LIMIT 1""", id=book_id)


def get_detail(s: Session, book_id: int) -> dict[str, Any] | None:
    return _one(s, """
        SELECT b.id, b.audible_id, b.title, COALESCE(b.subtitle,'') AS subtitle,
               COALESCE(b.description,'') AS description, COALESCE(b.cover_url,'') AS cover_url,
               b.length_minutes, COALESCE(b.publisher,'') AS publisher,
               COALESCE(b.language,'') AS language, COALESCE(b.audible_rating,0) AS audible_rating,
               lb.download_status, lb.is_finished, lb.tags, lb.account_id,
               lb.is_hidden, lb.is_downloadable, lb.last_format, lb.file_path, b.has_pdf, lb.updated_at
        FROM books b JOIN library_books lb ON lb.book_id = b.id
        WHERE b.id = :id ORDER BY lb.is_deleted, lb.is_downloadable DESC, lb.id LIMIT 1""", id=book_id)


def series_of(s: Session, book_id: int) -> list[dict[str, str]]:
    return _rows(s, """
        SELECT s.name, COALESCE(sb.book_index,'') AS idx FROM series s
        JOIN series_books sb ON sb.series_id = s.id WHERE sb.book_id = :id ORDER BY sb.rowid""", id=book_id)


def genres(s: Session, book_ids: list[int]) -> dict[int, list[str]]:
    """Most specific genre names per book, in the order Audible lists them."""
    out: dict[int, list[str]] = {i: [] for i in book_ids}
    if book_ids:
        for r in _rows(s, """
            SELECT bc.book_id, c.name FROM book_categories bc JOIN categories c ON c.id = bc.category_id
            WHERE bc.book_id IN :ids ORDER BY bc.rowid""", ids=book_ids):
            if r["name"] not in out[r["book_id"]]:
                out[r["book_id"]].append(r["name"])
    return out


def contributors(s: Session, book_ids: list[int]) -> dict[int, dict[str, list[str]]]:
    """Authors and narrators per book, in Audible's order."""
    out: dict[int, dict[str, list[str]]] = {i: {"author": [], "narrator": []} for i in book_ids}
    if book_ids:
        for r in _rows(s, """
            SELECT bc.book_id, bc.role, c.name FROM book_contributors bc
            JOIN contributors c ON c.id = bc.contributor_id
            WHERE bc.book_id IN :ids ORDER BY bc.role, bc.sort_order, bc.rowid""", ids=book_ids):
            out[r["book_id"]].setdefault(r["role"], []).append(r["name"])
    return out


def download_meta(s: Session, book_id: int, account_id: int | None = None) -> dict[str, Any] | None:
    """The book's account and the raw values used for file naming."""
    return _one(s, """
        SELECT a.audible_account_id, a.id AS account_id, lb.id AS library_book_id, lb.file_path,
               lb.is_downloadable, b.audible_id, b.title,
               COALESCE(b.language,'') AS language, COALESCE(b.length_minutes,0) AS length_minutes,
               COALESCE(lb.date_added,'') AS date_added, COALESCE(b.date_published,'') AS date_published
        FROM accounts a
        JOIN library_books lb ON lb.account_id = a.id
        JOIN books b ON b.id = lb.book_id
        WHERE b.id = :book AND (:account IS NULL OR a.id = :account)
        ORDER BY lb.is_deleted, lb.is_downloadable DESC, lb.id LIMIT 1""", book=book_id, account=account_id)


# --- per-book state -----------------------------------------------------------------


def update_fields(s: Session, book_id: int, **fields: Any) -> None:
    """Update library_books columns (tags, is_finished, is_hidden) for a book."""
    allowed = {"tags", "is_finished", "is_hidden"}
    for column, value in fields.items():
        if column not in allowed:
            raise ValueError(column)
        s.execute(text(f"UPDATE library_books SET {column} = :v, updated_at = :now WHERE book_id = :id"),
                  {"v": value, "id": book_id, "now": now()})


def set_hidden(s: Session, book_ids: list[int], hidden: bool) -> None:
    if book_ids:
        _rows_exec(s, "UPDATE library_books SET is_hidden = :hidden, updated_at = :now WHERE book_id IN :ids",
                   hidden=int(hidden), ids=book_ids, now=now())


def mark_downloaded(s: Session, book_id: int, fmt: str, file_path: str | None = None) -> None:
    s.execute(text("""
        UPDATE library_books SET download_status = 'downloaded', last_downloaded = CURRENT_TIMESTAMP,
            last_format = :fmt, file_path = COALESCE(:path, file_path), updated_at = :now
        WHERE book_id = :id"""), {"fmt": fmt, "path": file_path, "id": book_id, "now": now()})


def mark_error(s: Session, book_id: int) -> None:
    s.execute(text("""
        UPDATE library_books SET download_status = 'error', updated_at = :now
        WHERE book_id = :id AND download_status != 'downloaded'"""), {"id": book_id, "now": now()})


def not_downloaded_books(s: Session) -> list[dict[str, Any]]:
    """The books without a downloaded file, with how many books in all share their title."""
    return _rows(s, """
        SELECT b.id, b.audible_id, b.title,
               (SELECT COUNT(*) FROM books same WHERE same.title = b.title) AS same_title
        FROM books b JOIN library_books lb ON lb.book_id = b.id
        WHERE lb.download_status != 'downloaded'""")


def downloaded_books(s: Session) -> list[dict[str, Any]]:
    """Every downloaded book with the path of its audio file as recorded, which may be missing or stale."""
    return _rows(s, """
        SELECT DISTINCT b.id AS book_id, b.audible_id, lb.file_path
        FROM books b JOIN library_books lb ON lb.book_id = b.id
        WHERE lb.download_status = 'downloaded'""")


def downloaded_files(s: Session) -> list[dict[str, Any]]:
    """Every downloaded book with the path of its audio file, as recorded."""
    return _rows(s, """
        SELECT b.id AS book_id, b.audible_id, b.title, MAX(lb.file_path) AS file_path
        FROM books b JOIN library_books lb ON lb.book_id = b.id
        WHERE lb.download_status = 'downloaded' AND lb.file_path IS NOT NULL
        GROUP BY b.id ORDER BY b.id""")


def set_file_path(s: Session, book_id: int, file_path: str) -> None:
    s.execute(text("UPDATE library_books SET file_path = :path, updated_at = :now WHERE book_id = :id"),
              {"path": file_path, "id": book_id, "now": now()})


def has_downloaded_books(s: Session) -> bool:
    return bool(_rows(s, "SELECT 1 FROM library_books WHERE download_status = 'downloaded' LIMIT 1"))


def export_rows(s: Session) -> list[dict[str, Any]]:
    """Every book still in a library, with the columns the export needs."""
    return _rows(s, """
        SELECT b.id, b.audible_id, b.title, COALESCE(b.length_minutes,0) AS length_minutes,
               COALESCE(b.publisher,'') AS publisher, COALESCE(b.language,'') AS language,
               COALESCE(b.audible_rating,0) AS audible_rating, lb.download_status, lb.is_finished,
               lb.tags, lb.date_added
        FROM books b JOIN library_books lb ON lb.book_id = b.id
        WHERE lb.is_deleted = 0 ORDER BY b.title""")


def series_names(s: Session, book_ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {i: [] for i in book_ids}
    if book_ids:
        for r in _rows(s, """
            SELECT sb.book_id, s.name FROM series s JOIN series_books sb ON sb.series_id = s.id
            WHERE sb.book_id IN :ids ORDER BY sb.rowid""", ids=book_ids):
            out[r["book_id"]].append(r["name"])
    return out
