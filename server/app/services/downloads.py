"""Downloads: queueing, cancelling and retrying them, and recording how they go.

A download runs as two tasks, download_book then decrypt_book
(app/tasks/downloads.py). This service owns the downloads table; the
handlers report through it.

- Status changes are saved at once, percentages at most every
  PROGRESS_SAVE_INTERVAL seconds; list() overlays the fresher in-memory values.
- Finished downloads are kept as history (the newest HISTORY_LIMIT).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from ..audible_api.client import AudibleClient
from ..audible_api.content import ContentError
from ..config import FORMATS, Config
from ..db import Database, iso_utc
from ..db.models import Download, DownloadStatus
from ..jobs.download import INCOMPLETE_DIR, FileEntry, Target, discard_bundle, prune_work_dir, read_fetched_bundle
from ..jobs.filename import FilenameData, book_directory, render_filename
from ..repositories import books as books_repo
from ..repositories import downloads as repo
from ..tasks.downloads import DecryptBook, DownloadBook, DownloadPayload
from .library import LibraryService, naming_data
from .task_queue import TaskQueueService

log = logging.getLogger(__name__)

HISTORY_LIMIT = 500
PROGRESS_SAVE_INTERVAL = 3.0  # seconds
BUNDLE_MAX_AGE = 7 * 24 * 3600  # fetched bundles nobody retried are deleted after this (seconds)
INTERRUPTED = "Interrupted; download again"


class InvalidOptions(ValueError):
    pass


class NoPdf(Exception):
    """The title has no companion PDF."""


class PdfFailed(Exception):
    """Audible couldn't provide the PDF; the message says why."""


class _Rollback(Exception):
    """Abandon the current transaction, including any task it queued."""


class DownloadEvents:
    """Live download events for WebSocket subscribers, until phase 3's event
    stream. emit() is safe to call from any thread."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def emit(self, event: dict[str, Any]) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._deliver, dict(event))

    def _deliver(self, event: dict[str, Any]) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # a slow client misses a tick; the next one catches up


class DownloadsService:
    def __init__(self, db: Database, config: Config, tasks: TaskQueueService, events: DownloadEvents,
                 audible: AudibleClient, library: LibraryService):
        self._db = db
        self._config = config
        self._tasks = tasks
        self._events = events
        self._audible = audible
        self._library = library
        self._live: dict[str, dict[str, Any]] = {}  # running downloads: status, percent, message
        self._static: dict[str, dict[str, Any]] = {}  # running downloads: book_id, title, format
        self._last_saved: dict[str, float] = {}

    @property
    def work_dir(self) -> str:
        return os.path.join(self._config.output_dir, INCOMPLETE_DIR)

    def start(self) -> None:
        """At startup: fail downloads whose task is gone; prune history and old bundles."""
        self._events.attach(asyncio.get_running_loop())
        with self._db.session() as s:
            orphans = repo.fail_orphans(s, INTERRUPTED)
            pruned = repo.prune_finished(s, HISTORY_LIMIT)
        removed = prune_work_dir(self.work_dir, BUNDLE_MAX_AGE)
        if orphans:
            log.info("marked %d download(s) with no live task as failed", len(orphans))
        if pruned or removed:
            log.info("pruned %d old download(s) and %d old work file(s)", pruned, removed)

    # --- queueing, cancelling, retrying, listing ---------------------------------------------

    def enqueue(self, book_id: int, *, format: str = "", split_chapters: bool = False,  # noqa: A002
                account_id: int | None = None) -> str | None:
        """Queue one book. Returns the download id (the existing one if the book
        is already queued or running), or None if the book isn't in that library.
        format: m4b or mp3; "" means the default from Settings."""
        fmt = self._format(format)
        meta = self._library.book_meta(book_id, account_id)
        if meta is None:
            return None
        with self._db.session() as s:
            download_id = self._add(s, meta, fmt, split_chapters)
        self._emit(download_id)
        return download_id

    def enqueue_many(self, book_ids: list[int], *, format: str = "",  # noqa: A002
                     split_chapters: bool = False) -> list[dict[str, Any]]:
        """Queue several books in the order given; duplicates and unknown ids are skipped."""
        self._format(format)  # validate before queueing anything
        queued = []
        for book_id in dict.fromkeys(book_ids):
            if download_id := self.enqueue(book_id, format=format, split_chapters=split_chapters):
                queued.append({"job_id": download_id, "book_id": book_id})
        return queued

    def cancel(self, download_id: str) -> bool:
        """Cancel a queued or running download. False if it isn't active."""
        with self._db.session() as s:
            download = repo.cancel(s, download_id)
            task_id = download.task_id if download else None
        if download is None:
            return False
        if task_id:
            self._tasks.cancel(task_id)  # stops a running handler at once
        discard_bundle(self.work_dir, download_id)
        self._forget(download_id)
        self._emit(download_id)
        return True

    def retry(self, download_id: str) -> bool:
        """Run a failed download again: decrypt only if its fetched bundle is
        still there, otherwise from the start. False if it isn't failed."""
        task_cls = DecryptBook if read_fetched_bundle(self.work_dir, download_id) else DownloadBook
        try:
            with self._db.session() as s:
                task_id = self._tasks.enqueue(task_cls(payload=DownloadPayload(download_id=download_id)), session=s)
                if not repo.requeue(s, download_id, task_id):
                    raise _Rollback
        except _Rollback:
            return False
        self._emit(download_id)
        return True

    def list(self) -> list[dict[str, Any]]:
        """Active downloads and recent history, oldest first."""
        with self._db.session() as s:
            return [self._view(d, book_id, title) for d, book_id, title in repo.recent(s, HISTORY_LIMIT)]

    # --- the companion PDF on its own (no task, no download row) ------------------------------

    async def save_pdf(self, book_id: int, account_id: int | None = None) -> str | None:
        """Fetch a book's companion PDF and save it next to its audiobook, or
        where a download would put it. Returns the file's path, or None if the
        book isn't in that library. Raises NoPdf or PdfFailed."""
        meta = await asyncio.to_thread(self._library.book_meta, book_id, account_id)
        if meta is None:
            return None
        try:
            pdf = await self._audible.get_pdf(meta["audible_account_id"], meta["audible_id"])
        except ContentError as e:
            raise PdfFailed(str(e)) from e
        if not pdf:
            raise NoPdf
        return await asyncio.to_thread(self._store_pdf, meta, pdf)

    # --- reporting (called by the task handlers) ---------------------------------------------

    def target(self, download_id: str) -> Target | None:
        """What the pipeline needs; None if the download isn't active (cancelled meanwhile)."""
        with self._db.session() as s:
            info = repo.run_info(s, download_id)
        if info is None or info["download"].status not in repo.ACTIVE:
            return None
        d = info["download"]
        self._static[download_id] = {"book_id": info["book_id"], "title": info["title"], "format": str(d.format)}
        return Target(download_id=download_id, audible_account_id=info["audible_account_id"],
                      audible_id=info["audible_id"], title=info["title"], format=str(d.format),
                      split_chapters=d.split_chapters, path=d.path, base_name=d.base_name, has_pdf=info["has_pdf"])

    def report_progress(self, download_id: str, status: str, percent: float = 0, message: str = "") -> None:
        """Broadcast every call; save status changes at once and percentages at
        most every PROGRESS_SAVE_INTERVAL seconds."""
        live: dict[str, Any] = {"status": str(status), "percent": round(percent, 1)}
        if message:
            live["message"] = message
        previous = self._live.get(download_id)
        now = time.monotonic()
        changed = previous is None or (previous["status"], previous.get("message")) != (live["status"], message or None)
        if changed or now - self._last_saved.get(download_id, 0) >= PROGRESS_SAVE_INTERVAL:
            self._last_saved[download_id] = now
            with self._db.session() as s:
                if not repo.set_progress(s, download_id, DownloadStatus(status), live["percent"]):
                    self._forget(download_id)  # no longer active: cancelled
                    return
        # Only after saving: list() (another thread) overlays this on the saved
        # row, so it must never see a status the database doesn't have yet.
        self._live[download_id] = live
        self._events.emit({"job_id": download_id, **self._static.get(download_id, {}), **live})

    def chain_decrypt(self, download_id: str) -> bool:
        """The fetch is done: queue decrypt_book and move to decrypting, in one
        transaction. False if the download was cancelled meanwhile."""
        try:
            with self._db.session() as s:
                task_id = self._tasks.enqueue(DecryptBook(payload=DownloadPayload(download_id=download_id)), session=s)
                if not repo.set_progress(s, download_id, DownloadStatus.DECRYPTING, 100):
                    raise _Rollback
                repo.set_task(s, download_id, task_id)
        except _Rollback:
            discard_bundle(self.work_dir, download_id)  # cancelled while fetching
            return False
        self._forget(download_id)
        self._emit(download_id)
        return True

    def finish(self, download_id: str, files: list[FileEntry]) -> None:
        """Done: record the manifest and mark the book downloaded, in one transaction."""
        with self._db.session() as s:
            info = repo.run_info(s, download_id)
            if info and repo.finish(s, download_id, json.dumps([asdict(f) for f in files])):
                d = info["download"]
                books_repo.mark_downloaded(s, info["book_id"], str(d.format), _audio_path(d))
        discard_bundle(self.work_dir, download_id)
        self._forget(download_id)
        self._emit(download_id)

    def fail(self, download_id: str, error: str) -> None:
        """Failed for good: record why and mark the book failed, in one
        transaction. The fetched bundle, if any, stays for Retry."""
        with self._db.session() as s:
            info = repo.run_info(s, download_id)
            if info and repo.fail(s, download_id, error):
                books_repo.mark_error(s, info["book_id"])
        self._forget(download_id)
        self._emit(download_id)

    # --- helpers -------------------------------------------------------------------------

    def _add(self, s, meta: dict[str, Any], fmt: str, split_chapters: bool) -> str:
        if existing := repo.active_for(s, meta["library_book_id"]):
            return existing.id
        settings = self._config.snapshot()  # where it goes is decided now
        names = FilenameData(**naming_data(meta))
        download_id = uuid.uuid4().hex
        task_id = self._tasks.enqueue(DownloadBook(payload=DownloadPayload(download_id=download_id)), session=s)
        repo.add(s, id=download_id, library_book_id=meta["library_book_id"], format=fmt,
                 split_chapters=split_chapters, task_id=task_id,
                 path=book_directory(settings.output_dir, settings.folder_template, names),
                 base_name=render_filename(settings.filename_template, names))
        return download_id

    def _store_pdf(self, meta: dict[str, Any], pdf: bytes) -> str:
        path = self._pdf_path(meta)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        partial = path + ".part"
        with open(partial, "wb") as f:
            f.write(pdf)
        os.replace(partial, path)
        self._add_pdf_to_manifest(meta["library_book_id"], path)
        return path

    def _pdf_path(self, meta: dict[str, Any]) -> str:
        """Next to the audio file when its location is known; otherwise where
        a download would put it with the current settings."""
        if meta["file_path"]:
            return os.path.splitext(meta["file_path"])[0] + ".pdf"
        settings = self._config.snapshot()
        names = FilenameData(**naming_data(meta))
        folder = book_directory(settings.output_dir, settings.folder_template, names)
        return os.path.join(folder, render_filename(settings.filename_template, names) + ".pdf")

    def _add_pdf_to_manifest(self, library_book_id: int, path: str) -> None:
        """Keep the latest finished download's manifest true: add or replace its PDF entry."""
        with self._db.session() as s:
            d = repo.latest_done(s, library_book_id)
            if d is None or os.path.dirname(path) != d.path:
                return  # no download, or the PDF went somewhere else
            files = [f for f in json.loads(d.files or "[]") if f["role"] != "pdf"]
            files.append(asdict(FileEntry("pdf", os.path.basename(path), os.path.getsize(path))))
            repo.set_files(s, d.id, json.dumps(files))

    def _format(self, fmt: str) -> str:
        fmt = fmt or self._config.default_format
        if fmt not in FORMATS:
            raise InvalidOptions("format must be 'm4b' or 'mp3'")
        return fmt

    def _forget(self, download_id: str) -> None:
        self._live.pop(download_id, None)
        self._static.pop(download_id, None)
        self._last_saved.pop(download_id, None)

    def _emit(self, download_id: str) -> None:
        with self._db.session() as s:
            info = repo.run_info(s, download_id)
        if info:
            self._events.emit(self._view(info["download"], info["book_id"], info["title"]))

    def _view(self, d: Download, book_id: int, title: str) -> dict[str, Any]:
        """A download as the API and the WebSocket present it (`job_id` until phase 3)."""
        view: dict[str, Any] = {
            "job_id": d.id, "book_id": book_id, "title": title, "format": str(d.format),
            "status": str(d.status), "percent": round(d.percent or 0, 1),
            "created_at": iso_utc(d.created_at), "finished_at": iso_utc(d.finished_at),
            "files": json.loads(d.files) if d.files else None,
        }
        if d.status == DownloadStatus.FAILED and d.error:
            view["message"] = d.error
        elif d.status == DownloadStatus.DONE:
            view["message"] = _audio_path(d)
        if live := self._live.get(d.id):  # fresher than the database while it runs
            view.update(live)
        return view


def _audio_path(d: Download) -> str:
    return os.path.join(d.path, f"{d.base_name}.{d.format}")
