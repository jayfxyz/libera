"""Downloads: what the Downloads page shows, one row per download of a library book."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Row, delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..db.models import Account, Book, Download, DownloadStatus, LibraryBook, Task, TaskStatus
from .tasks import now

ACTIVE = (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING, DownloadStatus.DECRYPTING)
FINISHED = (DownloadStatus.DONE, DownloadStatus.FAILED, DownloadStatus.CANCELLED)


def add(s: Session, *, id: str, library_book_id: int, format: str, split_chapters: bool,  # noqa: A002
        path: str, base_name: str, task_id: str) -> None:
    s.add(Download(id=id, library_book_id=library_book_id, format=format, split_chapters=split_chapters,
                   path=path, base_name=base_name, task_id=task_id, status=DownloadStatus.QUEUED, percent=0,
                   created_at=now(), updated_at=now()))


def get(s: Session, download_id: str) -> Download | None:
    return s.get(Download, download_id)


def active_for(s: Session, library_book_id: int) -> Download | None:
    """The book's queued or running download, if any (the duplicate rule)."""
    return s.scalars(select(Download).where(Download.library_book_id == library_book_id,
                                            Download.status.in_(ACTIVE))
                     .order_by(Download.created_at).limit(1)).first()


def latest_done(s: Session, library_book_id: int) -> Download | None:
    """The book's most recent finished download."""
    return s.scalars(select(Download).where(Download.library_book_id == library_book_id,
                                            Download.status == DownloadStatus.DONE)
                     .order_by(Download.finished_at.desc()).limit(1)).first()


def set_files(s: Session, download_id: str, files: str) -> None:
    s.execute(update(Download).where(Download.id == download_id).values(files=files, updated_at=now()))


def run_info(s: Session, download_id: str) -> dict[str, Any] | None:
    """What a handler needs: the download plus the book's ASIN and title and the account's token key."""
    row = s.execute(
        select(Download, LibraryBook.book_id, Book.audible_id, Book.title, Book.has_pdf, Account.audible_account_id)
        .join(LibraryBook, LibraryBook.id == Download.library_book_id)
        .join(Book, Book.id == LibraryBook.book_id)
        .join(Account, Account.id == LibraryBook.account_id)
        .where(Download.id == download_id)).first()
    if row is None:
        return None
    download, *rest = row
    return {"download": download, **dict(zip(("book_id", "audible_id", "title", "has_pdf", "audible_account_id"), rest))}


def set_task(s: Session, download_id: str, task_id: str) -> None:
    s.execute(update(Download).where(Download.id == download_id).values(task_id=task_id, updated_at=now()))


def set_progress(s: Session, download_id: str, status: DownloadStatus, percent: float) -> bool:
    """Only while the download is active, so a late tick can't revive a cancelled one."""
    values: dict[str, Any] = {"status": status, "percent": percent, "updated_at": now()}
    if status != DownloadStatus.QUEUED:
        values["started_at"] = func.coalesce(Download.started_at, now())
    result = s.execute(update(Download).where(Download.id == download_id, Download.status.in_(ACTIVE))
                       .values(**values))
    return result.rowcount > 0


def finish(s: Session, download_id: str, files: str) -> bool:
    result = s.execute(update(Download).where(Download.id == download_id, Download.status.in_(ACTIVE))
                       .values(status=DownloadStatus.DONE, percent=100, error=None, files=files,
                               finished_at=now(), updated_at=now()))
    return result.rowcount > 0


def fail(s: Session, download_id: str, error: str) -> bool:
    result = s.execute(update(Download).where(Download.id == download_id, Download.status.in_(ACTIVE))
                       .values(status=DownloadStatus.FAILED, error=error, finished_at=now(), updated_at=now()))
    return result.rowcount > 0


def cancel(s: Session, download_id: str) -> Download | None:
    """Cancel an active download; returns it (with its task_id), or None if it wasn't active."""
    result = s.execute(update(Download).where(Download.id == download_id, Download.status.in_(ACTIVE))
                       .values(status=DownloadStatus.CANCELLED, finished_at=now(), updated_at=now()))
    return s.get(Download, download_id, populate_existing=True) if result.rowcount else None


def requeue(s: Session, download_id: str, task_id: str) -> bool:
    """Retry a failed download with a new task: back to queued, same row and location."""
    result = s.execute(update(Download).where(Download.id == download_id,
                                              Download.status == DownloadStatus.FAILED)
                       .values(status=DownloadStatus.QUEUED, percent=0, error=None, files=None,
                               task_id=task_id, started_at=None, finished_at=None, updated_at=now()))
    return result.rowcount > 0


def fail_orphans(s: Session, error: str) -> list[str]:
    """Active downloads with no live task (none, or it finished) become failed. Returns their ids."""
    live = select(Task.id).where(Task.status.in_((TaskStatus.PENDING, TaskStatus.PROCESSING)))
    return list(s.scalars(
        update(Download)
        .where(Download.status.in_(ACTIVE), or_(Download.task_id.is_(None), Download.task_id.not_in(live)))
        .values(status=DownloadStatus.FAILED, error=error, finished_at=now(), updated_at=now())
        .returning(Download.id)))


def recent(s: Session, limit: int) -> list[Row]:
    """Active downloads plus the newest `limit` finished ones, oldest first,
    each as (Download, book_id, title)."""
    base = (select(Download, LibraryBook.book_id, Book.title)
            .join(LibraryBook, LibraryBook.id == Download.library_book_id)
            .join(Book, Book.id == LibraryBook.book_id))
    active = s.execute(base.where(Download.status.in_(ACTIVE))).all()
    finished = s.execute(base.where(Download.status.in_(FINISHED))
                         .order_by(Download.finished_at.desc(), Download.created_at.desc()).limit(limit)).all()
    return sorted([*active, *finished], key=lambda r: r[0].created_at or "")


def prune_finished(s: Session, keep: int) -> int:
    """Delete finished downloads beyond the newest `keep`."""
    keep_ids = select(Download.id).where(Download.status.in_(FINISHED)).order_by(
        Download.finished_at.desc(), Download.created_at.desc()).limit(keep)
    result = s.execute(delete(Download).where(Download.status.in_(FINISHED), Download.id.not_in(keep_ids)))
    return result.rowcount
