import asyncio

import pytest

from app.jobs import queue as queue_module
from app.jobs.queue import DownloadJob, DownloadQueue
from app.services import library
from tests.conftest import add_account, make_book


@pytest.fixture
def books(db):
    add_account(db)
    library.import_library(db, 1, [make_book(f"B{i}", title=f"Book {i}") for i in range(1, 4)])
    return {r["audible_id"]: r["id"] for r in db.query("SELECT id, audible_id FROM books")}


def job(i: str, book_id: int) -> DownloadJob:
    return DownloadJob(id=i, book_id=book_id, audible_id="A", account_id=1, audible_account_id="x",
                       title=f"T{i}", format="m4b", output_dir="/tmp", filename_template="{title}", folder_template="")


async def wait_for(predicate, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.01)


def statuses(q):
    return {j["job_id"]: j["status"] for j in q.list_jobs()}


async def test_runs_jobs_and_broadcasts_progress(db, books):
    async def runner(q, j):
        q.set_status(j.id, "downloading", 50)
        q.set_status(j.id, "done", 100, "/out/T.m4b")

    q = DownloadQueue(runner, db, workers=1)
    events = q.subscribe()
    q.start()
    await q.enqueue(job("job-1", books["B1"]))
    await wait_for(lambda: statuses(q).get("job-1") == "done")
    seen = [events.get_nowait() for _ in range(events.qsize())]
    assert [e["status"] for e in seen] == ["queued", "downloading", "done"]
    assert {k: seen[-1][k] for k in ("job_id", "book_id", "title", "kind", "format", "percent", "message")} == {
        "job_id": "job-1", "book_id": books["B1"], "title": "Tjob-1", "kind": "audio", "format": "m4b",
        "percent": 100, "message": "/out/T.m4b"}
    listed = q.list_jobs()[0]
    assert listed["created_at"].endswith("Z") and listed["finished_at"].endswith("Z")
    await q.stop()


async def test_cancel_running_and_queued_jobs(db, books):
    started = asyncio.Event()

    async def runner(q, j):
        started.set()
        await asyncio.sleep(60)

    q = DownloadQueue(runner, db, workers=1)
    q.start()
    await q.enqueue(job("job-1", books["B1"]))
    await q.enqueue(job("job-2", books["B2"]))  # waits behind job-1
    await started.wait()

    assert await q.cancel("job-2") is True  # queued
    assert await q.cancel("job-1") is True  # running
    await wait_for(lambda: set(statuses(q).values()) == {"error"})
    assert {j["message"] for j in q.list_jobs()} == {"Cancelled"}
    assert await q.cancel("job-1") is False and await q.cancel("nope") is False
    await q.stop()


async def test_runner_exception_does_not_kill_worker(db, books):
    async def runner(q, j):
        if j.id == "job-1":
            raise RuntimeError("boom")
        q.set_status(j.id, "done", 100)

    q = DownloadQueue(runner, db, workers=1)
    q.start()
    await q.enqueue(job("job-1", books["B1"]))
    await q.enqueue(job("job-2", books["B2"]))
    await wait_for(lambda: statuses(q).get("job-2") == "done")
    assert next(j for j in q.list_jobs() if j["job_id"] == "job-1")["message"] == "Unexpected error: boom"
    await q.stop()


async def test_jobs_run_in_the_order_they_were_queued(db, books):
    order = []

    async def runner(q, j):
        order.append(j.id)
        q.set_status(j.id, "done", 100)

    q = DownloadQueue(runner, db, workers=1)
    for i, asin in enumerate(["B3", "B1", "B2"]):  # queued in one burst, before any worker runs
        await q.enqueue(job(f"job-{i}", books[asin]))
    q.start()
    await wait_for(lambda: len(order) == 3)
    assert order == ["job-0", "job-1", "job-2"]
    await q.stop()


async def test_queued_and_interrupted_jobs_survive_a_restart(db, books):
    started = asyncio.Event()

    async def slow(q, j):
        q.set_status(j.id, "downloading", 40)
        started.set()
        await asyncio.sleep(60)

    first = DownloadQueue(slow, db, workers=1)
    first.start()
    await first.enqueue(job("job-1", books["B1"]))
    await first.enqueue(job("job-2", books["B2"]))
    await started.wait()
    await first.stop()  # the app shuts down mid-download
    assert statuses(first) == {"job-1": "downloading", "job-2": "queued"}

    ran = []

    async def fast(q, j):
        ran.append((j.id, j.title, j.trace_context))
        q.set_status(j.id, "done", 100)

    second = DownloadQueue(fast, db, workers=1)
    second.start()  # interrupted job-1 is queued again, ahead of job-2
    await wait_for(lambda: set(statuses(second).values()) == {"done"})
    assert [r[0] for r in ran] == ["job-1", "job-2"]
    assert ran[0][1] == "Tjob-1" and ran[0][2] is None  # rebuilt from the database
    await second.stop()


async def test_cancelled_queued_job_stays_cancelled_after_restart(db, books):
    q = DownloadQueue(lambda q, j: asyncio.sleep(0), db, workers=0)  # no workers: jobs stay queued
    q.start()
    await q.enqueue(job("job-1", books["B1"]))
    assert await q.cancel("job-1") is True
    await q.stop()
    later = DownloadQueue(lambda q, j: asyncio.sleep(0), db, workers=1)
    later.start()
    await asyncio.sleep(0.1)
    assert statuses(later) == {"job-1": "error"}
    await later.stop()


async def test_history_is_pruned_at_startup(db, books, monkeypatch):
    monkeypatch.setattr(queue_module, "HISTORY_LIMIT", 2)

    async def runner(q, j):
        q.set_status(j.id, "done", 100)

    q = DownloadQueue(runner, db, workers=1)
    q.start()
    for i in range(4):
        await q.enqueue(job(f"job-{i}", books["B1"]))
    # (the listing itself is capped at HISTORY_LIMIT, so count in the database)
    await wait_for(lambda: db.scalar("SELECT COUNT(*) FROM jobs WHERE status = 'done'") == 4)
    await q.stop()

    restarted = DownloadQueue(runner, db, workers=1)
    restarted.start()
    assert sorted(statuses(restarted)) == ["job-2", "job-3"]  # the newest two
    await restarted.stop()


async def test_progress_is_saved_at_most_every_few_seconds(db, books, monkeypatch):
    saved = []
    original = queue_module.repo.update_status
    monkeypatch.setattr(queue_module.repo, "update_status", lambda s, *a: (saved.append(a), original(s, *a)))
    release = asyncio.Event()

    async def runner(q, j):
        for pct in range(0, 100, 10):
            q.set_status(j.id, "downloading", pct)  # status unchanged after the first
        await release.wait()

    q = DownloadQueue(runner, db, workers=1)
    q.start()
    await q.enqueue(job("job-1", books["B1"]))
    await wait_for(lambda: q.list_jobs()[0]["percent"] == 90)  # live value from memory
    assert [a[1] for a in saved] == ["downloading"]  # only the status change hit the database
    release.set()
    await q.stop()


async def test_stop_cancels_in_flight_work(db, books):
    async def runner(q, j):
        await asyncio.sleep(60)

    q = DownloadQueue(runner, db, workers=2)
    q.start()
    await q.enqueue(job("job-1", books["B1"]))
    await asyncio.sleep(0.05)
    await asyncio.wait_for(q.stop(), 2)
