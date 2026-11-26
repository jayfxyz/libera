"""The task queue: the tasks table behind one interface. Producers enqueue and
cancel; workers claim tasks and record how they ended. It never talks to the
workers except through TaskSignals (a wake-up and a cancel nudge)."""

from __future__ import annotations

import logging
import uuid

from opentelemetry import context as otel_context
from sqlalchemy import event
from sqlalchemy.orm import Session

from ..db import Database
from ..db.models import Task
from ..repositories import tasks as repo
from ..tasks.base import BaseTask
from ..tasks.signals import TaskSignals

log = logging.getLogger(__name__)

HISTORY_LIMIT = 500  # finished tasks kept


class TaskQueueService:
    def __init__(self, db: Database, signals: TaskSignals):
        self._db = db
        self._signals = signals

    def enqueue(self, task: BaseTask, session: Session | None = None) -> str:
        """Add a task; returns its id. Blocking (a database write): from async
        code call it in a thread.

        With a `session` the row joins the caller's transaction, so it is
        queued if and only if the caller commits; workers are woken after the
        commit."""
        task_id = uuid.uuid4().hex
        self._signals.remember_trace(task_id, otel_context.get_current())
        fields = dict(id=task_id, type=task.name, payload=task.payload.model_dump_json(),
                      max_attempts=task.max_attempts)
        if session is None:
            with self._db.session() as s:
                repo.add(s, **fields)
            self._signals.nudge(task.name)
        else:
            repo.add(session, **fields)
            session.flush()  # written now (not committed), so the caller's rows can reference it
            event.listen(session, "after_commit", lambda _s: self._signals.nudge(task.name), once=True)
            event.listen(session, "after_rollback", lambda _s: self._signals.forget(task_id), once=True)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task (a cancelled task is never retried).
        False if it was already finished or doesn't exist."""
        with self._db.session() as s:
            cancelled = repo.cancel(s, task_id)
        if cancelled:
            self._signals.request_cancel(task_id)  # stops the handler now, if it runs in this process
            self._signals.forget(task_id)
        return cancelled

    # --- the worker side -----------------------------------------------------
    # Each call is one short transaction and blocks: workers call them in a thread.

    def recover(self, *, history_limit: int = HISTORY_LIMIT) -> None:
        """At startup, before any worker: put back tasks the last shutdown
        interrupted (single process: anything still `processing` was) and drop
        old finished ones."""
        with self._db.session() as s:
            released = repo.release_stale(s, repo.now())
            pruned = repo.prune_finished(s, history_limit)
        if released:
            log.info("re-queued %d task(s) interrupted by the last shutdown", released)
        if pruned:
            log.info("pruned %d old finished task(s)", pruned)

    def claim(self, *, task_type: str) -> Task | None:
        """Take the oldest due pending task of this type and mark it processing."""
        with self._db.session() as s:
            return repo.claim_next(s, types=(task_type,))

    def heartbeat(self, task_id: str) -> bool:
        """Refresh the task's lock. False if it is no longer processing (cancelled meanwhile)."""
        with self._db.session() as s:
            return repo.heartbeat(s, task_id)

    def is_processing(self, task_id: str) -> bool:
        with self._db.session() as s:
            row = repo.get(s, task_id)
            return row is not None and row.status == "processing"

    def complete(self, task_id: str) -> None:
        with self._db.session() as s:
            repo.complete(s, task_id)

    def fail(self, task_id: str, *, error: str, retry: bool, retry_delay: float) -> str | None:
        """Record a failure. With `retry` and attempts left the task goes back to pending,
        not claimed for `retry_delay` seconds; otherwise it is failed. Returns the new
        status; None if the task wasn't processing (cancelled meanwhile)."""
        with self._db.session() as s:
            return repo.fail(s, task_id, error, retry, not_before=repo.later(retry_delay))

    def defer(self, task_id: str, *, reason: str, delay: float) -> None:
        """Put the task back for `delay` seconds without using up an attempt."""
        with self._db.session() as s:
            repo.defer(s, task_id, reason, repo.later(delay))
