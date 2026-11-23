"""DownloadsService and the two download tasks, with a fake pipeline."""

import asyncio
import os
import time
from types import SimpleNamespace

import pytest

from app.config import NamingPreset
from app.jobs.download import DownloadFailed, discard_bundle, read_fetched_bundle
from app.repositories import downloads as downloads_repo
from app.services import downloads as downloads_module
from app.services.library import LibraryService
from app.events import EventBus
from app.services.downloads import INTERRUPTED, DownloadsService, InvalidOptions
from app.services.task_queue import TaskQueueService
from app.services.task_worker import TaskWorkerService
from app.tasks.downloads import DownloadHandlers
from app.tasks.signals import TaskSignals
from tests.conftest import add_account, make_book, import_books


@pytest.fixture
def books(db):
    add_account(db)
    import_books(db, 1, [make_book(f"B{i}", title=f"Book {i}", authors=["Jane Author"]) for i in (1, 2)])
    return {r["audible_id"]: r["id"] for r in db.query("SELECT id, audible_id FROM books")}


@pytest.fixture
async def make_stack(db, config, pipeline):
    """The services wired as the app does (one worker). start=False leaves
    them unstarted. Every worker is stopped when the test ends."""
    workers = []

    def build(start=True):
        signals = TaskSignals()
        worker = TaskWorkerService(db, signals, workers=1, cancel_poll=0.02, retry_base_delay=0, idle_poll=0.05)
        bus = EventBus()
        bus.attach(asyncio.get_running_loop())
        svc = DownloadsService(db, config, TaskQueueService(db, signals), bus, audible=None,
                               library=LibraryService(db, config, bus))
        DownloadHandlers(svc, pipeline).register(worker)
        workers.append(worker)
        stack = SimpleNamespace(svc=svc, worker=worker, bus=bus, start=lambda: (worker.start(), svc.start()))
        if start:
            stack.start()
        return stack

    yield build
    for w in workers:
        await w.stop()


async def wait_for(predicate, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.01)


def row(db, download_id):
    return db.query_one("SELECT * FROM downloads WHERE id = ?", (download_id,))


def status(db, download_id):
    return db.scalar("SELECT status FROM downloads WHERE id = ?", (download_id,))


def tasks_settled(db):
    """No task pending or running: a download's last step (and its cleanup) is over."""
    return db.scalar("SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'processing')") == 0


async def read_all(subscription, timeout=0.1):
    """Every event waiting for this subscription."""
    events = []
    while True:
        try:
            events.append(await asyncio.wait_for(subscription.next(), timeout))
        except asyncio.TimeoutError:
            return events


# --- the happy path ------------------------------------------------------------------

async def test_a_download_is_fetched_then_decrypted(db, books, config, pipeline, make_stack):
    stack = make_stack()
    with stack.bus.subscribe() as subscription:
        download_id = stack.svc.enqueue(books["B1"])
        await wait_for(lambda: status(db, download_id) == "done" and tasks_settled(db))
        events = await read_all(subscription)

    assert [t.download_id for t in pipeline.fetched] == [t.download_id for t in pipeline.decrypted] == [download_id]
    book_dir = os.path.join(config.output_dir, "Jane Author - Book 1")
    t = pipeline.decrypted[0]
    assert (t.path, t.base_name, t.format, t.audible_account_id) == (book_dir, "Book 1", "m4b", "amzn1.account.TEST")
    view = stack.svc.list()[0]
    assert (view["status"], view["message"], view["files"]) == (
        "done", os.path.join(book_dir, "Book 1.m4b"), [{"role": "audio", "name": "Book 1.m4b", "size_bytes": 1}])
    assert view["created_at"].endswith("Z") and view["finished_at"].endswith("Z")
    lib = db.query_one("SELECT liberation_status, last_format, file_path FROM library_books WHERE book_id = ?",
                       (books["B1"],))
    assert dict(lib) == {"liberation_status": "liberated", "last_format": "m4b",
                         "file_path": os.path.join(book_dir, "Book 1.m4b")}
    assert [(r["type"], r["status"]) for r in db.query("SELECT type, status FROM tasks ORDER BY created_at")] == [
        ("download_book", "completed"), ("decrypt_book", "completed")]
    assert read_fetched_bundle(stack.svc.work_dir, download_id) is None  # gone once done
    # Read only at the end: each resource's latest state, the earlier ones coalesced away.
    assert [(e.type, e.id, e.data.get("status") or e.data.get("liberation_status")) for e in events] == [
        ("download.updated", download_id, "done"), ("book.updated", str(books["B1"]), "liberated")]
    assert events[0].data == view  # the same shape as REST


async def test_where_it_goes_is_decided_when_queued(db, books, config, pipeline, make_stack):
    stack = make_stack(start=False)
    download_id = stack.svc.enqueue(books["B1"], format="mp3", split_chapters=True)
    config.naming = NamingPreset.AUTHOR_FOLDER  # changed while it waits
    stack.start()
    await wait_for(lambda: status(db, download_id) == "done")
    t = pipeline.decrypted[0]
    assert (t.path, t.base_name, t.format, t.split_chapters) == (
        os.path.join(config.output_dir, "Jane Author - Book 1"), "Book 1", "mp3", True)


async def test_two_books_with_the_same_name_get_separate_folders(db, books, config, make_stack):
    import_books(db, 1, [make_book(f"T{i}", title="Twin", authors=["Jane Author"]) for i in (1, 2)])
    ids = [r["id"] for r in db.query("SELECT id FROM books WHERE audible_id IN ('T1', 'T2') ORDER BY audible_id")]
    stack = make_stack(start=False)
    first, second = (stack.svc.enqueue(book_id) for book_id in ids)
    paths = {r["id"]: r["path"] for r in db.query("SELECT id, path FROM downloads")}
    folder = os.path.join(config.output_dir, "Jane Author - Twin")
    assert (paths[first], paths[second]) == (folder, f"{folder} (2)")


async def test_queueing_a_book_twice_returns_the_active_download(db, books, make_stack):
    stack = make_stack(start=False)
    first = stack.svc.enqueue(books["B1"])
    assert stack.svc.enqueue(books["B1"]) == first
    assert db.scalar("SELECT COUNT(*) FROM downloads") == 1 and db.scalar("SELECT COUNT(*) FROM tasks") == 1
    stack.start()
    await wait_for(lambda: status(db, first) == "done")
    assert stack.svc.enqueue(books["B1"]) != first  # a finished download doesn't count


async def test_unknown_book_and_bad_format(db, books, make_stack):
    stack = make_stack(start=False)
    assert stack.svc.enqueue(999) is None
    with pytest.raises(InvalidOptions):
        stack.svc.enqueue(books["B1"], format="wav")


# --- cancelling ----------------------------------------------------------------------

async def test_cancel_a_running_and_a_queued_download(db, books, pipeline, make_stack):
    started = asyncio.Event()

    async def hang(t, report):
        started.set()
        await asyncio.sleep(60)

    pipeline.on_fetch = hang
    stack = make_stack()
    running = stack.svc.enqueue(books["B1"])
    waiting = stack.svc.enqueue(books["B2"])  # one worker: waits behind
    await asyncio.wait_for(started.wait(), 3)
    assert stack.svc.cancel(waiting) and stack.svc.cancel(running)
    await wait_for(lambda: db.scalar("SELECT COUNT(*) FROM tasks WHERE status = 'cancelled'") == 2)
    await asyncio.sleep(0.1)
    assert (status(db, running), status(db, waiting)) == ("cancelled", "cancelled")
    assert [t.download_id for t in pipeline.fetched] == [running] and pipeline.decrypted == []
    assert db.scalar("SELECT COUNT(*) FROM library_books WHERE liberation_status != 'not_liberated'") == 0
    assert not stack.svc.cancel(running) and not stack.svc.cancel("nope")


async def test_a_late_progress_report_cannot_revive_a_cancelled_download(db, books, make_stack):
    stack = make_stack(start=False)
    download_id = stack.svc.enqueue(books["B1"])
    stack.svc.cancel(download_id)
    stack.svc.report_progress(download_id, "downloading", 60)
    assert status(db, download_id) == "cancelled" and stack.svc.list()[0]["status"] == "cancelled"


# --- failures and retries --------------------------------------------------------------

async def test_network_errors_are_retried_then_the_download_fails(db, books, pipeline, make_stack):
    async def flaky(t, report):
        raise DownloadFailed("download: connection reset", retry=True)

    pipeline.on_fetch = flaky
    stack = make_stack()
    download_id = stack.svc.enqueue(books["B1"])
    await wait_for(lambda: status(db, download_id) == "failed")
    assert len(pipeline.fetched) == 3  # DownloadBook.max_attempts
    assert row(db, download_id)["error"] == "download: connection reset"
    assert db.scalar("SELECT liberation_status FROM library_books WHERE book_id = ?", (books["B1"],)) == "error"


async def test_a_refused_license_is_not_retried(db, books, pipeline, make_stack):
    async def refused(t, report):
        raise DownloadFailed("get download info: 403")

    pipeline.on_fetch = refused
    stack = make_stack()
    download_id = stack.svc.enqueue(books["B1"])
    await wait_for(lambda: status(db, download_id) == "failed")
    await asyncio.sleep(0.1)
    assert len(pipeline.fetched) == 1


def throttled_until(pipeline, refusals: int):
    """on_fetch: Audible refuses the first `refusals` licenses as throttled."""
    async def fetch(t, report):
        if len(pipeline.fetched) <= refusals:
            raise DownloadFailed("get download info: Audible refused the download license (\"throttled\")",
                                 throttled=True)
    return fetch


async def test_a_throttled_account_pauses_and_its_other_downloads_wait_without_asking(
        db, books, pipeline, make_stack):
    pipeline.on_fetch = throttled_until(pipeline, refusals=1)
    stack = make_stack()
    stack.svc.pauses = downloads_module.AccountPauses((0.4,))
    with stack.bus.subscribe() as sub:
        first, second = stack.svc.enqueue(books["B1"]), stack.svc.enqueue(books["B2"])
        await wait_for(lambda: any(e.data.get("retry_at") for e in sub._pending.values()))
        waiting = next(e.data for e in sub._pending.values() if e.data.get("retry_at"))
        await wait_for(lambda: status(db, first) == "done" and status(db, second) == "done", timeout=5)
    assert waiting["status"] == "queued" and "throttling" in waiting["message"]
    # B1 was refused once and asked again after the pause; B2 waited instead of asking meanwhile.
    assert [t.download_id for t in pipeline.fetched] == [first, first, second]
    assert db.scalar("SELECT MAX(attempts) FROM tasks WHERE type = 'download_book'") == 1  # waits are free
    assert stack.svc.pauses.wait(pipeline.fetched[0].audible_account_id) == 0  # cleared by the success


async def test_after_the_last_pause_the_accounts_downloads_fail_until_asked_again(
        db, books, pipeline, make_stack):
    pipeline.on_fetch = throttled_until(pipeline, refusals=2)
    stack = make_stack()
    stack.svc.pauses = downloads_module.AccountPauses((0.2,))
    first, second = stack.svc.enqueue(books["B1"]), stack.svc.enqueue(books["B2"])
    await wait_for(lambda: status(db, first) == "failed" and status(db, second) == "failed", timeout=5)
    assert [t.download_id for t in pipeline.fetched] == [first, first]  # B2 failed without asking
    assert "remove the account" in row(db, second)["error"]

    assert stack.svc.retry(second)  # asking again tries Audible again (which now says yes)
    await wait_for(lambda: status(db, second) == "done")


async def test_retry_failed_retries_each_books_latest_failed_download(db, books, pipeline, make_stack):
    async def refused(t, report):
        raise DownloadFailed("get download info: 403")

    pipeline.on_fetch = refused
    stack = make_stack()
    old = stack.svc.enqueue(books["B1"])
    await wait_for(lambda: status(db, old) == "failed")
    pipeline.on_fetch = None
    done = stack.svc.enqueue(books["B1"])  # B1 downloaded since: its old failure doesn't count
    await wait_for(lambda: status(db, done) == "done")
    pipeline.on_fetch = refused
    failed = stack.svc.enqueue(books["B2"])
    await wait_for(lambda: status(db, failed) == "failed")

    pipeline.on_fetch = None
    assert stack.svc.retry_failed() == [failed]
    await wait_for(lambda: status(db, failed) == "done")
    assert status(db, old) == "failed"


async def test_a_failed_decrypt_keeps_the_bundle_and_retry_only_decrypts(db, books, pipeline, make_stack):
    failures = ["ffmpeg: boom"]

    async def broken_once(t, report):
        if failures:
            raise DownloadFailed(failures.pop())

    pipeline.on_decrypt = broken_once
    stack = make_stack()
    download_id = stack.svc.enqueue(books["B1"])
    await wait_for(lambda: status(db, download_id) == "failed")
    assert row(db, download_id)["error"] == "ffmpeg: boom"
    assert read_fetched_bundle(stack.svc.work_dir, download_id) is not None  # kept for the retry

    assert stack.svc.retry(download_id) is True
    await wait_for(lambda: status(db, download_id) == "done")
    assert (len(pipeline.fetched), len(pipeline.decrypted)) == (1, 2)  # not downloaded again
    assert stack.svc.retry(download_id) is False  # only a failed download can be retried


async def test_retry_without_the_bundle_downloads_again(db, books, pipeline, make_stack):
    failures = ["ffmpeg: boom"]

    async def broken_once(t, report):
        if failures:
            raise DownloadFailed(failures.pop())

    pipeline.on_decrypt = broken_once
    stack = make_stack()
    download_id = stack.svc.enqueue(books["B1"])
    await wait_for(lambda: status(db, download_id) == "failed")
    discard_bundle(stack.svc.work_dir, download_id)  # e.g. cleaned up after 7 days
    assert stack.svc.retry(download_id) is True
    await wait_for(lambda: status(db, download_id) == "done")
    assert (len(pipeline.fetched), len(pipeline.decrypted)) == (2, 2)


async def test_an_unexpected_error_in_decrypt_fails_the_download(db, books, pipeline, make_stack):
    async def bug(t, report):
        raise RuntimeError("oops")

    pipeline.on_decrypt = bug
    stack = make_stack()
    download_id = stack.svc.enqueue(books["B1"])
    await wait_for(lambda: status(db, download_id) == "failed")
    await asyncio.sleep(0.1)
    assert row(db, download_id)["error"] == "Unexpected error: oops"
    assert len(pipeline.decrypted) == 1  # decrypt_book has no automatic retry


# --- progress, restarts, startup ---------------------------------------------------------

async def test_progress_is_saved_at_most_every_few_seconds(db, books, pipeline, make_stack, monkeypatch):
    saved = []
    original = downloads_repo.set_progress
    monkeypatch.setattr(downloads_repo, "set_progress",
                        lambda s, i, st, pct: (saved.append(str(st)), original(s, i, st, pct))[1])
    release = asyncio.Event()

    async def ticking(t, report):
        for pct in range(60, 100, 10):
            report("downloading", pct)  # status unchanged
        await release.wait()

    pipeline.on_fetch = ticking
    stack = make_stack()
    download_id = stack.svc.enqueue(books["B1"])
    await wait_for(lambda: stack.svc.list()[0]["percent"] == 90)  # the live value, from memory
    assert saved == ["downloading"]  # only the status change reached the database
    assert row(db, download_id)["percent"] == 50
    release.set()


async def test_an_interrupted_download_runs_again_after_a_restart(db, books, pipeline, make_stack):
    started = asyncio.Event()

    async def hang(t, report):
        started.set()
        await asyncio.sleep(60)

    pipeline.on_fetch = hang
    first = make_stack()
    download_id = first.svc.enqueue(books["B1"])
    await asyncio.wait_for(started.wait(), 3)
    await first.worker.stop()  # the app shuts down mid-download
    assert status(db, download_id) == "downloading"

    pipeline.on_fetch = None
    make_stack()  # restart: the task is released (not counted as an attempt) and runs again
    await wait_for(lambda: status(db, download_id) == "done")
    assert len(pipeline.fetched) == 2


async def test_downloads_left_without_a_live_task_fail_at_startup(db, books, make_stack):
    stack = make_stack(start=False)
    orphan = stack.svc.enqueue(books["B1"])
    waiting = stack.svc.enqueue(books["B2"])
    db.execute("UPDATE tasks SET status = 'failed' WHERE id = (SELECT task_id FROM downloads WHERE id = ?)",
               (orphan,))
    stack.svc.start()  # only the service: with no worker, nothing runs
    assert (status(db, orphan), row(db, orphan)["error"]) == ("failed", INTERRUPTED)
    assert status(db, waiting) == "queued"


async def test_history_and_old_work_files_are_pruned_at_startup(db, books, make_stack, monkeypatch):
    monkeypatch.setattr(downloads_module, "HISTORY_LIMIT", 2)
    stack = make_stack(start=False)
    ids = []
    for _ in range(4):
        ids.append(stack.svc.enqueue(books["B1"]))
        stack.svc.cancel(ids[-1])  # finished, so the next enqueue makes a new download
    work = stack.svc.work_dir
    os.makedirs(work, exist_ok=True)
    for name in ("old.aaxc", "fresh.aaxc"):
        open(os.path.join(work, name), "wb").close()
    eight_days_ago = time.time() - 8 * 24 * 3600
    os.utime(os.path.join(work, "old.aaxc"), (eight_days_ago, eight_days_ago))

    stack.svc.start()
    assert {r["id"] for r in db.query("SELECT id FROM downloads")} == set(ids[2:])  # the newest two
    assert os.listdir(work) == ["fresh.aaxc"]
