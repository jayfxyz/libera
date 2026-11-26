"""Background tasks (the generic queue)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Collection, Sequence

from sqlalchemy import bindparam, delete, literal, select, text, update
from sqlalchemy.orm import Session

from ..db.models import Task


def now() -> str:
    """UTC, to the microsecond, in SQLite's text format, so tasks queued in the
    same second still sort in the order they were queued."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def later(seconds: float) -> str:
    """now() plus `seconds`, in the same format (so the two compare as text)."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")


FINISHED = ("completed", "failed", "cancelled")


def add(s: Session, *, id: str, type: str, payload: str, max_attempts: int = 1) -> None:  # noqa: A002
    s.add(Task(id=id, type=type, payload=payload, status="pending", attempts=0,
               max_attempts=max_attempts, created_at=now()))


def claim_next(s: Session, types: Sequence[str] | None = None) -> Task | None:
    """Take the oldest pending task that is due (of one of `types`, if given) and
    mark it processing, in one statement, so two workers can't take the same task."""
    if types is not None and not types:
        return None
    sql = f"""
        UPDATE tasks SET status = 'processing', attempts = attempts + 1, locked_at = :now
        WHERE id = (SELECT id FROM tasks WHERE status = 'pending'
                    AND (not_before IS NULL OR not_before <= :now)
                    {"AND type IN :types" if types else ""}
                    ORDER BY created_at, rowid LIMIT 1)
          AND status = 'pending'
        RETURNING id"""
    stmt = text(sql)
    params: dict = {"now": now()}
    if types:
        stmt = stmt.bindparams(bindparam("types", expanding=True))
        params["types"] = list(types)
    task_id = s.execute(stmt, params).scalar()
    return s.get(Task, task_id, populate_existing=True) if task_id else None


def heartbeat(s: Session, task_id: str) -> bool:
    """Refresh locked_at. False if the task is no longer processing (cancelled meanwhile)."""
    result = s.execute(update(Task).where(Task.id == task_id, Task.status == "processing")
                       .values(locked_at=now()))
    return result.rowcount > 0


def complete(s: Session, task_id: str) -> bool:
    result = s.execute(update(Task).where(Task.id == task_id, Task.status == "processing")
                       .values(status="completed", locked_at=None, finished_at=now()))
    return result.rowcount > 0


def fail(s: Session, task_id: str, error: str, retry: bool, not_before: str | None = None) -> str | None:
    """Record a failure. With `retry` and attempts left the task goes back to
    pending (not claimed before `not_before`), otherwise it is failed. Returns
    the new status; None if the task wasn't processing (e.g. cancelled meanwhile)."""
    return s.execute(text("""
        UPDATE tasks SET
          status = CASE WHEN :retry AND attempts < max_attempts THEN 'pending' ELSE 'failed' END,
          finished_at = CASE WHEN :retry AND attempts < max_attempts THEN NULL ELSE :now END,
          not_before = CASE WHEN :retry AND attempts < max_attempts THEN :not_before ELSE not_before END,
          locked_at = NULL, error = :error
        WHERE id = :id AND status = 'processing'
        RETURNING status"""),
        {"retry": int(retry), "now": now(), "error": error, "id": task_id, "not_before": not_before}).scalar()


def defer(s: Session, task_id: str, reason: str, not_before: str) -> bool:
    """Put a processing task back to pending, not claimed before `not_before`, giving back the
    attempt it was claimed with. False if it wasn't processing (cancelled meanwhile)."""
    result = s.execute(text("""
        UPDATE tasks SET status = 'pending', attempts = MAX(attempts - 1, 0), locked_at = NULL,
          not_before = :not_before, error = :reason
        WHERE id = :id AND status = 'processing'"""), {"not_before": not_before, "reason": reason, "id": task_id})
    return result.rowcount > 0


def cancel(s: Session, task_id: str) -> bool:
    """Cancel a pending or processing task. False if it is already finished or unknown."""
    result = s.execute(update(Task).where(Task.id == task_id, Task.status.in_(("pending", "processing")))
                       .values(status="cancelled", locked_at=None, finished_at=now()))
    return result.rowcount > 0


def release_stale(s: Session, older_than: str) -> int:
    """Processing tasks locked before `older_than` go back to pending without
    consuming an attempt (the interrupted run doesn't count)."""
    result = s.execute(text("""
        UPDATE tasks SET status = 'pending', attempts = MAX(attempts - 1, 0), locked_at = NULL
        WHERE status = 'processing' AND (locked_at IS NULL OR locked_at < :cutoff)"""),
        {"cutoff": older_than})
    return result.rowcount


def fail_unknown_types(s: Session, known_types: Collection[str]) -> int:
    """Pending tasks of a type outside `known_types` (no handler, so no worker)
    are failed, rather than waiting forever."""
    result = s.execute(update(Task).where(Task.status == "pending", Task.type.not_in(known_types))
                       .values(status="failed", error=literal("Unknown task type: ") + Task.type,
                               locked_at=None, finished_at=now()))
    return result.rowcount


def prune_finished(s: Session, keep: int) -> int:
    """Delete finished tasks beyond the newest `keep`."""
    keep_ids = select(Task.id).where(Task.status.in_(FINISHED)).order_by(
        Task.finished_at.desc(), Task.created_at.desc()).limit(keep)
    result = s.execute(delete(Task).where(Task.status.in_(FINISHED), Task.id.not_in(keep_ids)))
    return result.rowcount


def get(s: Session, task_id: str) -> Task | None:
    return s.get(Task, task_id)
