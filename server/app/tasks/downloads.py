"""The two tasks of a download: download_book (fetch from Audible), then
decrypt_book (local only). The handlers are thin: the pipeline does the
work (app/jobs/download.py) and DownloadsService records it."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING, NoReturn

from pydantic import BaseModel

from ..jobs import download as steps
from ..jobs.download import DownloadFailed, FileEntry, Target
from .base import BaseTask, TaskContext, TaskDeferred, TaskFailed

if TYPE_CHECKING:
    from ..audible_api.client import AudibleClient
    from ..services.downloads import DownloadsService
    from ..services.task_worker import TaskWorkerService

log = logging.getLogger(__name__)

WAITING_FOR_AUDIBLE = "Audible is throttling this account; waiting before trying again."
GAVE_UP = ("Audible kept refusing downloads for this account (\"throttled\") for hours. This usually "
           "means its device registration is outdated: remove the account under Accounts and add it "
           "again (your library and downloads are kept), then retry.")


class DownloadPayload(BaseModel):
    download_id: str


class DownloadBook(BaseTask[DownloadPayload]):
    """Fetch: license, encrypted file and extras. Network errors are retried
    (after a growing pause); a throttled account's downloads wait (see AccountPauses)."""

    name = "download_book"
    max_attempts = 3


class DecryptBook(BaseTask[DownloadPayload]):
    """Decrypt the fetched bundle, locally. A failure needs a person (usually
    a code fix), so there's no automatic retry: the Retry button runs it again."""

    name = "decrypt_book"


class Pipeline:
    """The pipeline's two steps; tests pass a fake with the same methods."""

    def __init__(self, audible: AudibleClient):
        self._audible = audible

    async def fetch(self, t: Target, work_dir: str, report_progress) -> None:
        await steps.fetch(self._audible, t, work_dir, report_progress)

    async def decrypt(self, t: Target, work_dir: str, report_progress) -> list[FileEntry]:
        return await steps.decrypt(t, work_dir, report_progress)


class DownloadHandlers:
    """The two task handlers. Thin: the pipeline does the work, DownloadsService records it."""

    def __init__(self, downloads: DownloadsService, pipeline: Pipeline):
        self.downloads = downloads
        self.pipeline = pipeline

    def register(self, worker: TaskWorkerService) -> None:
        worker.register(DownloadBook, self.download_book)
        worker.register(DecryptBook, self.decrypt_book)

    async def download_book(self, payload: DownloadPayload, ctx: TaskContext) -> None:
        t = await self._target(payload)
        if t is None:
            return  # cancelled meanwhile
        await self._unless_paused(t)
        try:
            await self.pipeline.fetch(t, self.downloads.work_dir, self._reporter(t))
        except Exception as e:
            if isinstance(e, DownloadFailed) and e.throttled:
                await self._throttled(t)
            await self._failed(t, e, attempts_left=ctx.attempt < ctx.max_attempts)
        self.downloads.pauses.cleared(t.audible_account_id)  # Audible let one through
        await asyncio.to_thread(self.downloads.chain_decrypt, t.download_id)

    async def decrypt_book(self, payload: DownloadPayload, ctx: TaskContext) -> None:
        t = await self._target(payload)
        if t is None:
            return  # cancelled meanwhile
        try:
            files = await self.pipeline.decrypt(t, self.downloads.work_dir, self._reporter(t))
        except Exception as e:
            await self._failed(t, e, attempts_left=False)
        await asyncio.to_thread(self.downloads.finish, t.download_id, files)

    async def _target(self, payload: DownloadPayload) -> Target | None:
        return await asyncio.to_thread(self.downloads.target, payload.download_id)

    def _reporter(self, t: Target):
        """report_progress(status, percent, message) for this download."""
        return partial(self.downloads.report_progress, t.download_id)

    # --- an account Audible is throttling --------------------------------------------------

    async def _unless_paused(self, t: Target) -> None:
        """Before asking Audible: wait out the account's pause, or fail if we gave up on it."""
        pauses = self.downloads.pauses
        if pauses.gave_up(t.audible_account_id):
            await asyncio.to_thread(self.downloads.fail, t.download_id, GAVE_UP)
            raise TaskFailed(GAVE_UP)
        if (wait := pauses.wait(t.audible_account_id)) > 0:
            self._wait(t, wait)

    async def _throttled(self, t: Target) -> NoReturn:
        """Audible refused the license as throttled: pause the account (longer each
        time) and wait, or fail once the last pause didn't help."""
        pause = self.downloads.pauses.throttled(t.audible_account_id)
        if pause is None:
            await asyncio.to_thread(self.downloads.fail, t.download_id, GAVE_UP)
            raise TaskFailed(GAVE_UP)
        log.warning("download %s: Audible is throttling the account; pausing it for %.0f min",
                    t.download_id, pause / 60)
        self._wait(t, pause)

    def _wait(self, t: Target, seconds: float) -> NoReturn:
        """Show the download as waiting, and put its task back until then."""
        self.downloads.report_progress(t.download_id, "queued", 0, WAITING_FOR_AUDIBLE, retry_in=seconds)
        raise TaskDeferred(WAITING_FOR_AUDIBLE, seconds)

    async def _failed(self, t: Target, e: Exception, attempts_left: bool) -> NoReturn:
        """Turn a pipeline failure into a task failure: retried while worthwhile
        and attempts remain (the download shows as queued again); otherwise the
        download fails (and its bundle, if any, is kept for the Retry button)."""
        if isinstance(e, DownloadFailed):
            message, worth_retrying = str(e), e.retry
        else:  # a bug: log it, and treat it like a transient error
            log.exception("download %s: unexpected error", t.download_id)
            message, worth_retrying = f"Unexpected error: {e}", True
        if worth_retrying and attempts_left:
            self.downloads.report_progress(t.download_id, "queued", 0, f"Retrying after: {message}")
            raise TaskFailed(message, retry=True) from e
        await asyncio.to_thread(self.downloads.fail, t.download_id, message)
        raise TaskFailed(message) from e
