"""ORM models: the schema as Python. Alembic migrations (db/migrations) create it.

Date/time columns are mapped as strings: SQLite stores them as text, and
the values come in more than one shape (SQLite's "2026-11-08 23:00:51" and
Audible's "2026-11-08T22:13:33.125Z"); they're passed through unchanged.

The full-text index (books_fts, an FTS5 virtual table) can't be modelled;
it's created by the baseline migration and used with SQL in the books
repository.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import (Boolean, Enum, Float, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


NOW = text("CURRENT_TIMESTAMP")


def _enum(cls: type[StrEnum], name: str) -> Enum:
    """A StrEnum stored as its values in a text column, with a CHECK constraint."""
    return Enum(cls, name=name, native_enum=False, create_constraint=True,
                values_callable=lambda e: [m.value for m in e])


class Account(Base):
    """One Amazon login in one region: the same login in another region is another account."""
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("email", "locale"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)  # Amazon may give a user id instead
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
    has_pdf: Mapped[bool | None] = mapped_column(Boolean)  # from the library sync; None until synced
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
    is_downloadable: Mapped[int] = mapped_column(Integer, server_default="1")  # offline download rights on Audible
    # not_liberated | liberated | error (historical names; the UI says downloaded)
    liberation_status: Mapped[str] = mapped_column(Text, server_default="not_liberated")
    tags: Mapped[str] = mapped_column(Text, server_default="")
    user_rating: Mapped[float | None] = mapped_column(Float)
    is_finished: Mapped[int] = mapped_column(Integer, server_default="0")
    last_downloaded: Mapped[str | None] = mapped_column(String)
    last_format: Mapped[str | None] = mapped_column(Text)
    is_hidden: Mapped[int] = mapped_column(Integer, server_default="0")
    file_path: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(String)  # set on every change


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


class TaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Base):
    """A unit of background work for the task queue: what to run (type + payload)
    and how it went. Knows nothing about books or downloads."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # uuid4 hex
    type: Mapped[str] = mapped_column(Text)  # task name, e.g. "download_book"
    payload: Mapped[str] = mapped_column(Text)  # JSON, validated by the task's pydantic model
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus, "task_status"))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")  # incremented on claim
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="1")
    error: Mapped[str | None] = mapped_column(Text)  # last failure message
    created_at: Mapped[str] = mapped_column(String, server_default=NOW)
    locked_at: Mapped[str | None] = mapped_column(String)  # set on claim, refreshed while running
    not_before: Mapped[str | None] = mapped_column(String)  # workers don't claim it before this; NULL = no restriction
    finished_at: Mapped[str | None] = mapped_column(String)

    __table_args__ = (Index("ix_tasks_status_created", "status", "created_at"),)


class DownloadFormat(StrEnum):
    M4B = "m4b"
    MP3 = "mp3"


class DownloadStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DECRYPT_QUEUED = "decrypt_queued"  # fetched; waiting for a decrypt worker
    DECRYPTING = "decrypting"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Download(Base):
    """What the Downloads page shows: one download of one library book.

    `path` and `base_name` (where it goes) are decided when it is queued;
    `files` (what it wrote) is filled in when it is done."""

    __tablename__ = "downloads"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    library_book_id: Mapped[int] = mapped_column(ForeignKey("library_books.id", ondelete="CASCADE"))
    format: Mapped[DownloadFormat] = mapped_column(_enum(DownloadFormat, "download_format"))
    split_chapters: Mapped[bool] = mapped_column(Boolean, server_default="0")
    path: Mapped[str] = mapped_column(Text)  # the book's folder (absolute): every file goes here
    base_name: Mapped[str] = mapped_column(Text)  # file name without extension, e.g. "12 Rules for Life"
    status: Mapped[DownloadStatus] = mapped_column(_enum(DownloadStatus, "download_status"))
    percent: Mapped[float] = mapped_column(Float, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    files: Mapped[str | None] = mapped_column(Text)  # JSON [{role, name, size_bytes}], names within path
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))  # current task
    updated_at: Mapped[str | None] = mapped_column(String)  # set on every change
    created_at: Mapped[str] = mapped_column(String, server_default=NOW)
    started_at: Mapped[str | None] = mapped_column(String)
    finished_at: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        Index("ix_downloads_status_created", "status", "created_at"),
        Index("ix_downloads_library_book", "library_book_id"),
    )
