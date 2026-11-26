"""Running tasks: asyncio workers in the web process that claim tasks of one
type from the queue and run their handlers (looked up in the registry). They
read only the queue; TaskSignals is an optional accelerator.

- A handler is `async def handler(payload, ctx: TaskContext) -> None`.
- TaskFailed(message, retry=False) fails the task permanently; any other
  exception retries while attempts remain, after a growing pause
  (retry_base_delay, then 4x that, ..., with some jitter).
- TaskDeferred(message, delay) puts the task back for `delay` seconds
  without using up an attempt.
- A task interrupted by shutdown stays `processing` and is released by
  TaskQueueService.recover() at the next startup without losing an attempt.
- While a handler runs, the task's lock is refreshed every HEARTBEAT_INTERVAL
  and the task is checked every CANCEL_POLL: one cancelled by another process
  stops the handler.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import NamedTuple

from opentelemetry import context as otel_context
from pydantic import BaseModel

from ..db.models import Task
from ..tasks.base import TaskContext, TaskDeferred, TaskFailed
from ..tasks.registry import Handler, TaskRegistry
from ..tasks.signals import TaskSignals
from .task_queue import TaskQueueService

log = logging.getLogger(__name__)

IDLE_POLL = 30.0  # seconds; workers also wake as soon as something is enqueued
HEARTBEAT_INTERVAL = 30.0
CANCEL_POLL = 1.0
RETRY_BASE_DELAY = 30.0  # seconds before the 2nd attempt; each later one waits 4x longer


class Outcome(NamedTuple):
    """How a handler ended. The default is success."""

    error: str | None = None
    retry: bool = False
    defer: float | None = None  # seconds: put back without using up an attempt


class TaskWorker:
    """`concurrency` loops that each claim and run tasks of `task_type`, one at a time."""

    def __init__(self, *, queue: TaskQueueService, registry: TaskRegistry, signals: TaskSignals,
                 task_type: str, concurrency: int = 1,
                 idle_poll: float = IDLE_POLL, heartbeat_interval: float = HEARTBEAT_INTERVAL,
                 cancel_poll: float = CANCEL_POLL, retry_base_delay: float = RETRY_BASE_DELAY):
        self._queue = queue
        self._registry = registry
        self._signals = signals
        self.task_type = task_type
        self._concurrency = concurrency
        self._idle_poll = idle_poll
        self._heartbeat_interval = heartbeat_interval
        self._cancel_poll = cancel_poll
        self._retry_base_delay = retry_base_delay
        self._loops: list[asyncio.Task] = []

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._signals.attach(asyncio.get_running_loop())
        wake = self._signals.wake_for(self.task_type)
        for i in range(self._concurrency):
            self._loops.append(asyncio.create_task(
                self._loop(wake), name=f"task-worker-{self.task_type}-{i}"))

    async def stop(self) -> None:
        for t in self._loops:
            t.cancel()  # cancelling a loop also cancels the handler it is awaiting
        await asyncio.gather(*self._loops, return_exceptions=True)
        self._loops.clear()

    # --- the worker loop -----------------------------------------------------

    async def _loop(self, wake: asyncio.Event) -> None:
        """Claim and run tasks one after another; sleep when there are none."""
        while True:
            # Clear before looking: a task enqueued after the look sets it again,
            # so the wait below can't miss it.
            wake.clear()
            try:
                if await self.process():
                    continue  # busy: go straight back for the next task
            except Exception:  # e.g. the database is busy: the worker must survive
                log.exception("task worker error")
                await asyncio.sleep(1)
                continue
            try:  # idle: sleep until enqueue() wakes us, or the poll interval passes
                await asyncio.wait_for(wake.wait(), self._idle_poll)
            except asyncio.TimeoutError:
                pass

    async def process(self) -> bool:
        """Claim and run one task. False if none was pending."""
        task = await asyncio.to_thread(self._queue.claim, task_type=self.task_type)
        if task is None:
            return False
        await self._run(task)
        return True

    # --- running one task ----------------------------------------------------

    async def _run(self, task: Task) -> None:
        """Run a claimed task and record how it ended."""
        try:
            handler, payload = self._registry.prepare(task_type=task.type, payload=task.payload)
        except TaskFailed as e:  # can't even start: permanent
            await asyncio.to_thread(self._finish, task, Outcome(str(e)))
            return
        outcome = await self._execute(task, handler, payload)
        if outcome is not None:  # None: cancelled, the row already says so
            await asyncio.to_thread(self._finish, task, outcome)

    async def _execute(self, task: Task, handler: Handler, payload: BaseModel) -> Outcome | None:
        """Run the handler as its own asyncio task, next to a monitor task.

        Returns how it ended, or None if the task was cancelled. Shutdown
        (the worker itself being cancelled) is re-raised: the row stays
        `processing` and is released at the next startup."""
        ctx = TaskContext(task_id=task.id, attempt=task.attempts, max_attempts=task.max_attempts)
        trace = self._signals.trace_for(task.id)
        token = otel_context.attach(trace) if trace is not None else None
        work = asyncio.create_task(handler(payload, ctx), name=f"task-{task.id}")
        self._signals.set_running(task.id, work)  # so a cancel request can reach it
        monitor = asyncio.create_task(self._watch(task.id, work))
        try:
            await work
            return Outcome()
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise  # the worker is being stopped (shutdown)
            log.info("task %s (%s) cancelled", task.id, task.type)  # only the handler was cancelled
            self._signals.forget(task.id)
            return None
        except TaskFailed as e:
            return Outcome(str(e), e.retry)
        except TaskDeferred as e:
            return Outcome(str(e), defer=e.delay)
        except Exception as e:  # a bug in a handler must not kill the worker
            log.exception("task %s (%s) failed", task.id, task.type)
            return Outcome(f"{type(e).__name__}: {e}", retry=True)
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
            self._signals.set_running(task.id, None)
            if token is not None:
                otel_context.detach(token)

    def _finish(self, task: Task, outcome: Outcome) -> None:
        """Record the outcome, and log it."""
        status = self._record(task, outcome)
        if status == "deferred":
            log.info("task %s deferred for %.0fs: %s", task.id, outcome.defer, outcome.error)
        elif status == "pending":
            log.warning("task %s failed, will retry: %s", task.id, outcome.error)
        else:
            self._signals.forget(task.id)  # no retry coming

    def _record(self, task: Task, outcome: Outcome) -> str | None:
        """Write the outcome: completed, deferred, or failed (back to pending,
        after a pause, if it will retry). Returns the task's new status."""
        if outcome.defer is not None:
            self._queue.defer(task.id, reason=outcome.error or "", delay=outcome.defer)
            return "deferred"
        if outcome.error is None:
            self._queue.complete(task.id)
            return "completed"
        return self._queue.fail(task.id, error=outcome.error, retry=outcome.retry,
                                retry_delay=self.retry_delay(task.attempts))

    def retry_delay(self, attempt: int) -> float:
        """Seconds to wait after failed attempt number `attempt` (1-based): the
        base delay, 4x more each time, +-20% so retries don't line up."""
        return self._retry_base_delay * 4 ** (attempt - 1) * random.uniform(0.8, 1.2)

    # --- while a handler runs ------------------------------------------------

    async def _watch(self, task_id: str, work: asyncio.Task) -> None:
        """Refresh the task's lock, and stop the handler if the task was cancelled."""
        last_beat = time.monotonic()
        while True:
            await asyncio.sleep(self._cancel_poll)
            beat = time.monotonic() - last_beat >= self._heartbeat_interval
            try:
                alive = await asyncio.to_thread(self._still_processing, task_id, beat)
            except Exception:
                log.warning("task %s: could not check its row", task_id, exc_info=True)
                continue
            if beat:
                last_beat = time.monotonic()
            if not alive:
                work.cancel()
                return

    def _still_processing(self, task_id: str, beat: bool) -> bool:
        if beat:
            return self._queue.heartbeat(task_id)
        return self._queue.is_processing(task_id)
