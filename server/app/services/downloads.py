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
from datetime import datetime, timezone
from typing import Any

from ..audible_api.client import AudibleClient
from ..audible_api.content import ContentError
from ..config import FORMATS, Config
from ..db import Database, iso_utc
from ..db.models import Download, DownloadStatus
from ..events import EventBus
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
PROGRESS_EVENT_INTERVAL = 0.5  # seconds: about two progress events a second per download
BUNDLE_MAX_AGE = 7 * 24 * 3600  # fetched bundles nobody retried are deleted after this (seconds)
INTERRUPTED = "Interrupted; download again"
# When Audible throttles an account, its downloads wait this long, one pause after
# another while it keeps refusing (about 7 3/4 hours in all); then they fail.
THROTTLE_PAUSES = (15 * 60, 30 * 60, 60 * 60, 2 * 60 * 60, 4 * 60 * 60)


class InvalidOptions(ValueError):
    pass


class NoPdf(Exception):
    """The title has no companion PDF."""


class PdfFailed(Exception):
    """Audible couldn't provide the PDF; the message says why."""


class _Rollback(Exception):
    """Abandon the current transaction, including any task it queued."""


class AccountPauses:
    """Accounts Audible is throttling, by token key: until when their downloads
    wait, how many pauses in a row, and whether we gave up on them. In memory: a
    restart starts over (the tasks' own wait times are in the database)."""

    def __init__(self, pauses: tuple[float, ...] = THROTTLE_PAUSES):
        self._pauses = pauses
        self._until: dict[str, float] = {}
        self._rounds: dict[str, int] = {}
        self._gave_up: set[str] = set()

    def wait(self, key: str) -> float:
        """Seconds before this account's downloads may ask Audible again (0: now)."""
        return max(0.0, self._until.get(key, 0.0) - time.time())

    def gave_up(self, key: str) -> bool:
        return key in self._gave_up

    def throttled(self, key: str) -> float | None:
        """Audible refused a license as throttled: start the next, longer pause and
        return its length, or None after the last one (given up until cleared).
        Downloads already running when a pause started don't start another."""
        if (remaining := self.wait(key)) > 0:
            return remaining
        rounds = self._rounds.get(key, 0)
        if rounds >= len(self._pauses):
            self._until.pop(key, None)
            self._rounds.pop(key, None)
            self._gave_up.add(key)
            return None
        self._rounds[key] = rounds + 1
        self._until[key] = time.time() + self._pauses[rounds]
        return self._pauses[rounds]

    def cleared(self, key: str) -> None:
        """A download got through, or someone asked to try again: no more pausing."""
        self._until.pop(key, None)
        self._rounds.pop(key, None)
        self._gave_up.discard(key)


class DownloadsService:
    def __init__(self, db: Database, config: Config, tasks: TaskQueueService, events: EventBus,
                 audible: AudibleClient, library: LibraryService, pauses: AccountPauses | None = None):
        self._db = db
        self._config = config
        self._tasks = tasks
        self._events = events
        self._audible = audible
        self._library = library
        self.pauses = pauses or AccountPauses()
        self._live: dict[str, dict[str, Any]] = {}  # running downloads: status, percent, message
        self._static: dict[str, dict[str, Any]] = {}  # running downloads: the resource as last read
        self._last_saved: dict[str, float] = {}
        self._last_published: dict[str, float] = {}

    @property
    def work_dir(self) -> str:
        return os.path.join(self._config.output_dir, INCOMPLETE_DIR)

    def start(self) -> None:
        """At startup: fail downloads whose task is gone; prune history and old bundles."""
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
        if self.pauses.gave_up(meta["audible_account_id"]):
            self.pauses.cleared(meta["audible_account_id"])  # asked again: try Audible again
        self._emit(download_id)
        return download_id

    def enqueue_many(self, book_ids: list[int], *, format: str = "",  # noqa: A002
                     split_chapters: bool = False) -> list[dict[str, Any]]:
        """Queue several books in the order given; duplicates and unknown ids are skipped."""
        self._format(format)  # validate before queueing anything
        queued = []
        for book_id in dict.fromkeys(book_ids):
            if download_id := self.enqueue(book_id, format=format, split_chapters=split_chapters):
                queued.append({"id": download_id, "book_id": book_id})
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
                info = repo.run_info(s, download_id)
        except _Rollback:
            return False
        if info and self.pauses.gave_up(info["audible_account_id"]):
            self.pauses.cleared(info["audible_account_id"])  # asked again: try Audible again
        self._emit(download_id)
        return True

    def retry_failed(self) -> list[str]:
        """Retry every book whose latest download failed. Returns the ids queued again."""
        with self._db.session() as s:
            ids = repo.latest_failed(s)
        return [download_id for download_id in ids if self.retry(download_id)]

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
        self._static[download_id] = self._view(d, info["book_id"], info["title"])
        return Target(download_id=download_id, audible_account_id=info["audible_account_id"],
                      audible_id=info["audible_id"], title=info["title"], format=str(d.format),
                      split_chapters=d.split_chapters, path=d.path, base_name=d.base_name, has_pdf=info["has_pdf"])

    def report_progress(self, download_id: str, status: str, percent: float = 0, message: str = "",
                        retry_in: float | None = None) -> None:
        """Save status changes at once and percentages at most every
        PROGRESS_SAVE_INTERVAL; publish status changes at once and percentages
        at most every PROGRESS_EVENT_INTERVAL. retry_in: a waiting download's
        next try is that many seconds away (shown as retry_at)."""
        live: dict[str, Any] = {"status": str(status), "percent": round(percent, 1),
                                "updated_at": iso_utc(repo.now())}
        if message:
            live["message"] = message
        if retry_in is not None:
            live["retry_at"] = datetime.fromtimestamp(time.time() + retry_in, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        previous = self._live.get(download_id)
        now = time.monotonic()
        changed = previous is None or any(previous.get(k) != live.get(k) for k in ("status", "message", "retry_at"))
        if changed or now - self._last_saved.get(download_id, 0) >= PROGRESS_SAVE_INTERVAL:
            self._last_saved[download_id] = now
            with self._db.session() as s:
                if not repo.set_progress(s, download_id, DownloadStatus(status), live["percent"]):
                    self._forget(download_id)  # no longer active: cancelled
                    return
        # Only after saving: list() (another thread) overlays this on the saved
        # row, so it must never see a status the database doesn't have yet.
        self._live[download_id] = live
        if changed or now - self._last_published.get(download_id, 0) >= PROGRESS_EVENT_INTERVAL:
            self._last_published[download_id] = now
            self._events.publish("download.updated", download_id, {**self._static.get(download_id, {}), **live})

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
        if info:
            self._library.publish_book(info["book_id"])

    def fail(self, download_id: str, error: str) -> None:
        """Failed for good: record why and mark the book failed, in one
        transaction. The fetched bundle, if any, stays for Retry."""
        with self._db.session() as s:
            info = repo.run_info(s, download_id)
            if info and repo.fail(s, download_id, error):
                books_repo.mark_error(s, info["book_id"])
        self._forget(download_id)
        self._emit(download_id)
        if info:
            self._library.publish_book(info["book_id"])

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
        self._last_published.pop(download_id, None)

    def _emit(self, download_id: str) -> None:
        with self._db.session() as s:
            info = repo.run_info(s, download_id)
        if info:
            self._events.publish("download.updated", download_id,
                                 self._view(info["download"], info["book_id"], info["title"]))

    def _view(self, d: Download, book_id: int, title: str) -> dict[str, Any]:
        """A download as the API and the event stream present it."""
        view: dict[str, Any] = {
            "id": d.id, "book_id": book_id, "title": title, "format": str(d.format),
            "status": str(d.status), "percent": round(d.percent or 0, 1),
            "created_at": iso_utc(d.created_at), "finished_at": iso_utc(d.finished_at),
            "updated_at": iso_utc(d.updated_at),
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
