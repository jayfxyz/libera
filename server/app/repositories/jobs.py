"""Background jobs (the download queue and its history)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from ..db.models import Job

def now() -> str:
    """UTC, to the microsecond, in SQLite's text format: jobs queued in the same
    second (a bulk download) still sort in the order they were queued."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


ACTIVE = ("downloading", "decrypting")
FINISHED = ("done", "error")


def add(s: Session, *, id: str, type: str, title: str, book_id: int | None, payload: str) -> None:  # noqa: A002
    s.add(Job(id=id, type=type, status="queued", percent=0, title=title, book_id=book_id, payload=payload,
              created_at=now()))


def claim_next(s: Session) -> Job | None:
    """Take the oldest queued job and mark it started, in one statement (so two
    workers can't take the same job)."""
    row = s.execute(text("""
        UPDATE jobs SET status = 'downloading', percent = 0, message = NULL, started_at = :now
        WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1)
          AND status = 'queued'
        RETURNING id"""), {"now": now()}).scalar()
    return s.get(Job, row) if row else None


def update_status(s: Session, job_id: str, status: str, percent: float, message: str | None) -> None:
    values = {"status": status, "percent": percent, "message": message}
    if status in FINISHED:
        values["finished_at"] = now()
    s.execute(update(Job).where(Job.id == job_id).values(**values))


def cancel_queued(s: Session, job_id: str) -> bool:
    """Cancel a job that hasn't started. False if it isn't queued."""
    result = s.execute(update(Job).where(Job.id == job_id, Job.status == "queued").values(
        status="error", message="Cancelled", finished_at=now()))
    return result.rowcount > 0


def requeue_interrupted(s: Session) -> int:
    """Jobs that were running when the app stopped go back in the queue (they start over)."""
    result = s.execute(update(Job).where(Job.status.in_(ACTIVE)).values(
        status="queued", percent=0, message=None, started_at=None))
    return result.rowcount


def prune_finished(s: Session, keep: int) -> int:
    """Delete finished jobs beyond the newest `keep`."""
    keep_ids = select(Job.id).where(Job.status.in_(FINISHED)).order_by(
        Job.finished_at.desc(), Job.created_at.desc()).limit(keep)
    result = s.execute(delete(Job).where(Job.status.in_(FINISHED), Job.id.not_in(keep_ids)))
    return result.rowcount


def recent(s: Session, limit: int) -> list[Job]:
    """Unfinished jobs plus the newest finished ones, oldest first."""
    unfinished = list(s.scalars(select(Job).where(Job.status.not_in(FINISHED))))
    finished = list(s.scalars(select(Job).where(Job.status.in_(FINISHED))
                              .order_by(Job.finished_at.desc(), Job.created_at.desc()).limit(limit)))
    return sorted(unfinished + finished, key=lambda j: j.created_at or "")


def get(s: Session, job_id: str) -> Job | None:
    return s.get(Job, job_id)
