"""In-memory download queue: asyncio workers and progress broadcast."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from opentelemetry import context as otel_context

log = logging.getLogger(__name__)

STATUSES = ("queued", "downloading", "decrypting", "done", "error")


@dataclass
class DownloadJob:
    id: str
    book_id: int
    audible_id: str
    account_id: int
    audible_account_id: str  # token file key, e.g. amzn1.account.…
    title: str
    format: str
    output_dir: str
    filename_template: str
    folder_template: str
    authors: str = ""  # comma-separated
    narrators: str = ""
    series_name: str = ""
    series_index: str = ""
    language: str = ""
    year: str = ""
    duration_h: str = ""
    split_chapters: bool = False
    # Trace context of the request that enqueued the job, so job spans are its children.
    trace_context: Any = field(default=None, repr=False)


class DownloadQueue:
    def __init__(self, runner: Callable[["DownloadQueue", DownloadJob], Awaitable[None]], workers: int = 3):
        self._runner = runner
        self._workers = workers
        self._queue: asyncio.Queue[DownloadJob] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._running: dict[str, asyncio.Task] = {}
        self._cancelled_queued: set[str] = set()
        self._state: dict[str, dict[str, Any]] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._stopping = False

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._worker(), name=f"download-worker-{i}") for i in range(self._workers)]

    async def stop(self) -> None:
        self._stopping = True
        for t in [*self._running.values(), *self._tasks]:
            t.cancel()
        await asyncio.gather(*self._running.values(), *self._tasks, return_exceptions=True)
        self._tasks.clear()

    # --- jobs ------------------------------------------------------------------

    def enqueue(self, job: DownloadJob) -> None:
        if job.trace_context is None:
            job.trace_context = otel_context.get_current()
        self._state[job.id] = {"job_id": job.id, "book_id": job.book_id, "status": "queued", "percent": 0}
        self._queue.put_nowait(job)
        self._emit(self._state[job.id])

    def cancel(self, job_id: str) -> bool:
        """Stop a running or queued job. False if it isn't running or queued."""
        if task := self._running.get(job_id):
            task.cancel()
            return True
        state = self._state.get(job_id)
        if state and state["status"] == "queued" and job_id not in self._cancelled_queued:
            self._cancelled_queued.add(job_id)
            self.set_status(job_id, "error", 0, "Cancelled")
            return True
        return False

    def list_jobs(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self._state.values()]

    def set_status(self, job_id: str, status: str, percent: float = 0, message: str = "") -> None:
        state = self._state.setdefault(job_id, {"job_id": job_id, "book_id": 0})
        state.update(status=status, percent=round(percent, 1))
        if message:
            state["message"] = message
        else:
            state.pop("message", None)
        self._emit(state)

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job.id in self._cancelled_queued:
                    self._cancelled_queued.discard(job.id)
                    continue
                task = asyncio.create_task(self._run(job), name=f"download-{job.id}")
                self._running[job.id] = task
                try:
                    await task
                finally:
                    self._running.pop(job.id, None)
            finally:
                self._queue.task_done()

    async def _run(self, job: DownloadJob) -> None:
        token = otel_context.attach(job.trace_context) if job.trace_context is not None else None
        try:
            await self._runner(self, job)
        except asyncio.CancelledError:
            if self._stopping:
                raise  # shutting down: let the worker stop too
            log.info("job %s cancelled", job.id)
            self.set_status(job.id, "error", 0, "Cancelled")
        except Exception as e:  # a bug in the runner must not kill the worker
            log.exception("job %s failed", job.id)
            self.set_status(job.id, "error", 0, f"Unexpected error: {e}")
        finally:
            if token is not None:
                otel_context.detach(token)

    # --- progress broadcast ------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _emit(self, event: dict[str, Any]) -> None:
        snapshot = dict(event)
        for q in self._subscribers:
            try:
                q.put_nowait(snapshot)
            except asyncio.QueueFull:
                pass  # a slow client misses a progress tick; the next one catches up
