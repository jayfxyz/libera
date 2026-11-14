"""ORM models: the schema as Python. Alembic migrations (db/migrations) create it.

Date/time columns are mapped as strings: SQLite stores them as text, and
the values come in more than one shape (SQLite's "2026-11-08 23:00:51" and
Audible's "2026-11-08T22:13:33.125Z"); they're passed through unchanged.

The full-text index (books_fts, an FTS5 virtual table) can't be modelled;
it's created by the baseline migration and used with SQL in the books
repository.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


NOW = text("CURRENT_TIMESTAMP")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)  # Amazon may give a user id instead
    locale: Mapped[str] = mapped_column(Text)
    audible_account_id: Mapped[str] = mapped_column(Text, server_default="")  # token file key
    library_scan_enabled: Mapped[int] = mapped_column(Integer, server_default="1")
    last_scanned_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=NOW)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audible_id: Mapped[str] = mapped_column(Text, unique=True)  # ASIN
    title: Mapped[str] = mapped_column(Text)
    subtitle: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    length_minutes: Mapped[int] = mapped_column(Integer, server_default="0")
    content_type: Mapped[str] = mapped_column(Text, server_default="Product")
    locale: Mapped[str] = mapped_column(Text)
    is_abridged: Mapped[int] = mapped_column(Integer, server_default="0")
    is_spatial: Mapped[int] = mapped_column(Integer, server_default="0")
    date_published: Mapped[str | None] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    audible_rating: Mapped[float | None] = mapped_column(Float)
    audible_rating_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String, server_default=NOW)


class LibraryBook(Base):
    """A book in an account's library, with the per-account state."""

    __tablename__ = "library_books"
    __table_args__ = (UniqueConstraint("book_id", "account_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    date_added: Mapped[str] = mapped_column(String)
    is_deleted: Mapped[int] = mapped_column(Integer, server_default="0")  # gone from the Audible library
    is_audible_plus: Mapped[int] = mapped_column(Integer, server_default="0")
    # not_liberated | liberated | error (historical names; the UI says downloaded)
    liberation_status: Mapped[str] = mapped_column(Text, server_default="not_liberated")
    tags: Mapped[str] = mapped_column(Text, server_default="")
    user_rating: Mapped[float | None] = mapped_column(Float)
    is_finished: Mapped[int] = mapped_column(Integer, server_default="0")
    last_downloaded: Mapped[str | None] = mapped_column(String)
    last_format: Mapped[str | None] = mapped_column(Text)
    is_hidden: Mapped[int] = mapped_column(Integer, server_default="0")
    file_path: Mapped[str | None] = mapped_column(Text)


class Contributor(Base):
    __tablename__ = "contributors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audible_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, unique=True)


class BookContributor(Base):
    __tablename__ = "book_contributors"
    __table_args__ = (PrimaryKeyConstraint("book_id", "contributor_id", "role"),)

    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    contributor_id: Mapped[int] = mapped_column(ForeignKey("contributors.id"))
    role: Mapped[str] = mapped_column(Text)  # author | narrator
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audible_id: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)


class SeriesBook(Base):
    __tablename__ = "series_books"
    __table_args__ = (PrimaryKeyConstraint("series_id", "book_id"),)

    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"))
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    book_index: Mapped[str | None] = mapped_column(Text)


class Category(Base):
    """An Audible genre; parent_id makes the tree."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audible_id: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))


class BookCategory(Base):
    __tablename__ = "book_categories"
    __table_args__ = (PrimaryKeyConstraint("book_id", "category_id"),)

    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Job(Base):
    """A background job: today, downloads. Survives restarts; finished ones are history."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text)  # "download"
    status: Mapped[str] = mapped_column(Text)  # queued | downloading | decrypting | done | error
    percent: Mapped[float] = mapped_column(Float, server_default="0")
    message: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"))
    payload: Mapped[str] = mapped_column(Text)  # JSON
    created_at: Mapped[str] = mapped_column(String, server_default=NOW)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)

    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)


class Task(Base):
    """A unit of background work for the task queue: what to run (type + payload)
    and how it went. Knows nothing about books or downloads."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # uuid4 hex
    type: Mapped[str] = mapped_column(Text)  # task name, e.g. "download_book"
    payload: Mapped[str] = mapped_column(Text)  # JSON, validated by the task's pydantic model
    # pending | processing | completed | failed | cancelled
    status: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")  # incremented on claim
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="1")
    error: Mapped[str | None] = mapped_column(Text)  # last failure message
    created_at: Mapped[str] = mapped_column(String, server_default=NOW)
    locked_at: Mapped[str | None] = mapped_column(String)  # set on claim, refreshed while running
    finished_at: Mapped[str | None] = mapped_column(String)

    __table_args__ = (Index("ix_tasks_status_created", "status", "created_at"),)
