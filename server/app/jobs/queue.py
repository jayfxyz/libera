"""Download queue: jobs persisted in the `jobs` table, run by asyncio workers.

- Queued jobs survive restarts; jobs that were running when the app stopped
  are queued again on startup (they start over: work files are discarded).
- Status changes are written straight away; progress percentages at most
  every PROGRESS_SAVE_INTERVAL seconds. Live progress is broadcast to
  WebSocket subscribers from memory.
- Finished jobs are kept as history (the newest HISTORY_LIMIT).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from opentelemetry import context as otel_context

from ..db import Database, iso_utc
from ..repositories import jobs as repo

log = logging.getLogger(__name__)

STATUSES = ("queued", "downloading", "decrypting", "done", "error")
JOB_TYPE = "download"
HISTORY_LIMIT = 500
PROGRESS_SAVE_INTERVAL = 3.0  # seconds
IDLE_POLL = 30.0  # seconds; workers also wake as soon as something is queued


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
    include_pdf: bool = True  # also save the companion PDF, if the title has one
    kind: str = "audio"  # "audio", or "pdf" for the companion PDF only
    # Trace context of the request that enqueued the job, so job spans are its children.
    # Not persisted: a job resumed after a restart starts a new trace.
    trace_context: Any = field(default=None, repr=False, compare=False)

    def to_payload(self) -> str:
        data = dataclasses.asdict(self)
        data.pop("trace_context")
        return json.dumps(data)

    @classmethod
    def from_payload(cls, payload: str) -> "DownloadJob":
        data = json.loads(payload)
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def _event(row, live: dict[str, Any] | None = None) -> dict[str, Any]:
    """A job as the API and WebSocket present it."""
    payload = json.loads(row.payload)
    event = {
        "job_id": row.id,
        "book_id": row.book_id if row.book_id is not None else payload.get("book_id"),
        "title": row.title,
        "kind": payload.get("kind", "audio"),
        "format": payload.get("format"),
        "status": row.status,
        "percent": round(row.percent or 0, 1),
        "created_at": iso_utc(row.created_at),
        "finished_at": iso_utc(row.finished_at),
    }
    if row.message:
        event["message"] = row.message
    if live:  # fresher than the database for a running job
        event.update({k: v for k, v in live.items() if k in ("status", "percent", "message")})
        if "message" not in live:
            event.pop("message", None)
    return event


class DownloadQueue:
    def __init__(self, runner: Callable[["DownloadQueue", DownloadJob], Awaitable[None]], db: Database,
                 workers: int = 3):
        self._runner = runner
        self._db = db
        self._workers = workers
        self._tasks: list[asyncio.Task] = []
        self._running: dict[str, asyncio.Task] = {}
        self._live: dict[str, dict[str, Any]] = {}  # latest status of running jobs
        self._static: dict[str, dict[str, Any]] = {}  # fields that don't change while a job runs
        self._last_saved: dict[str, float] = {}
        self._traces: dict[str, Any] = {}  # trace context of jobs queued in this process
        self._wake = asyncio.Event()
        self._subscribers: set[asyncio.Queue] = set()
        self._stopping = False

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        with self._db.session() as s:
            resumed = repo.requeue_interrupted(s)
            pruned = repo.prune_finished(s, HISTORY_LIMIT)
        if resumed:
            log.info("re-queued %d download(s) interrupted by the last shutdown", resumed)
        if pruned:
            log.info("pruned %d old finished job(s)", pruned)
        self._tasks = [asyncio.create_task(self._worker(), name=f"download-worker-{i}") for i in range(self._workers)]

    async def stop(self) -> None:
        self._stopping = True
        for t in [*self._running.values(), *self._tasks]:
            t.cancel()
        await asyncio.gather(*self._running.values(), *self._tasks, return_exceptions=True)
        self._tasks.clear()

    # --- jobs ------------------------------------------------------------------

    async def enqueue(self, job: DownloadJob) -> None:
        self._traces[job.id] = job.trace_context if job.trace_context is not None else otel_context.get_current()
        await asyncio.to_thread(self._add, job)
        self._emit({"job_id": job.id, "book_id": job.book_id, "title": job.title, "kind": job.kind,
                    "format": job.format, "status": "queued", "percent": 0})
        self._wake.set()

    def _add(self, job: DownloadJob) -> None:
        with self._db.session() as s:
            repo.add(s, id=job.id, type=JOB_TYPE, title=job.title, book_id=job.book_id, payload=job.to_payload())

    async def cancel(self, job_id: str) -> bool:
        """Stop a running or queued job. False if it isn't running or queued."""
        if task := self._running.get(job_id):
            task.cancel()
            return True
        cancelled = await asyncio.to_thread(self._cancel_queued, job_id)
        if cancelled:
            self._emit(await asyncio.to_thread(self._event_for, job_id))
        return cancelled

    def _cancel_queued(self, job_id: str) -> bool:
        with self._db.session() as s:
            return repo.cancel_queued(s, job_id)

    def _event_for(self, job_id: str) -> dict[str, Any]:
        with self._db.session() as s:
            return _event(repo.get(s, job_id))

    def list_jobs(self) -> list[dict[str, Any]]:
        """Unfinished jobs and the recent history, oldest first."""
        with self._db.session() as s:
            return [_event(row, self._live.get(row.id)) for row in repo.recent(s, HISTORY_LIMIT)]

    def set_status(self, job_id: str, status: str, percent: float = 0, message: str = "") -> None:
        """Called by the runner. Broadcast now; save status changes now and
        progress at most every PROGRESS_SAVE_INTERVAL seconds."""
        previous = self._live.get(job_id, {})
        live: dict[str, Any] = {"status": status, "percent": round(percent, 1)}
        if message:
            live["message"] = message

        now = time.monotonic()
        changed = previous.get("status") != status or previous.get("message") != live.get("message")
        if changed or now - self._last_saved.get(job_id, 0) >= PROGRESS_SAVE_INTERVAL:
            self._last_saved[job_id] = now
            with self._db.session() as s:
                repo.update_status(s, job_id, status, live["percent"], message or None)
        # Only after saving: list_jobs (another thread) overlays this on the saved
        # row, so it must never see a status the database doesn't have yet.
        self._live[job_id] = live
        self._emit({"job_id": job_id, **self._static.get(job_id, {}), **live})

    async def _worker(self) -> None:
        while True:
            # Clear before looking: a job queued after the look sets it again,
            # so the wait below can't miss it.
            self._wake.clear()
            job = await asyncio.to_thread(self._claim)
            if job is None:
                try:
                    await asyncio.wait_for(self._wake.wait(), IDLE_POLL)
                except asyncio.TimeoutError:
                    pass
                continue
            task = asyncio.create_task(self._run(job), name=f"download-{job.id}")
            self._running[job.id] = task
            try:
                await task
            finally:
                self._running.pop(job.id, None)
                self._live.pop(job.id, None)
                self._last_saved.pop(job.id, None)
                self._static.pop(job.id, None)
                self._traces.pop(job.id, None)

    def _claim(self) -> DownloadJob | None:
        with self._db.session() as s:
            row = repo.claim_next(s)
            if row is None:
                return None
            job = DownloadJob.from_payload(row.payload)
        job.trace_context = self._traces.get(job.id)
        self._static[job.id] = {"book_id": job.book_id, "title": job.title, "kind": job.kind, "format": job.format}
        return job

    async def _run(self, job: DownloadJob) -> None:
        token = otel_context.attach(job.trace_context) if job.trace_context is not None else None
        try:
            await self._runner(self, job)
        except asyncio.CancelledError:
            if self._stopping:
                raise  # shutting down: the job is re-queued at next startup
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
