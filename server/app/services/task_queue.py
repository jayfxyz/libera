"""Enqueueing and cancelling tasks. Writes rows; never talks to the workers
except through TaskSignals (a wake-up and a cancel nudge)."""

from __future__ import annotations

import uuid

from opentelemetry import context as otel_context
from sqlalchemy import event
from sqlalchemy.orm import Session

from ..db import Database
from ..repositories import tasks as repo
from ..tasks.base import BaseTask
from ..tasks.signals import TaskSignals


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
            self._signals.nudge()
        else:
            repo.add(session, **fields)
            event.listen(session, "after_commit", lambda _s: self._signals.nudge(), once=True)
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
