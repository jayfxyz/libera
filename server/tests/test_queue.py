import asyncio

from app.jobs.queue import DownloadJob, DownloadQueue


def job(i: str) -> DownloadJob:
    return DownloadJob(id=i, book_id=int(i[-1]), audible_id="A", account_id=1, audible_account_id="x",
                       title="T", format="m4b", output_dir="/tmp", filename_template="{title}", folder_template="")


async def wait_for(predicate, timeout=2.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.01)


async def test_runs_jobs_and_broadcasts_progress():
    async def runner(q, j):
        q.set_status(j.id, "downloading", 50)
        q.set_status(j.id, "done", 100, "/out/T.m4b")

    q = DownloadQueue(runner, workers=1)
    events = q.subscribe()
    q.start()
    q.enqueue(job("job-1"))
    await wait_for(lambda: q.list_jobs()[0]["status"] == "done")
    seen = [events.get_nowait() for _ in range(events.qsize())]
    assert [e["status"] for e in seen] == ["queued", "downloading", "done"]
    assert seen[-1] == {"job_id": "job-1", "book_id": 1, "title": "T", "kind": "audio", "format": "m4b", "status": "done",
                        "percent": 100, "message": "/out/T.m4b"}
    assert "message" not in seen[0]
    await q.stop()


async def test_cancel_running_and_queued_jobs():
    started = asyncio.Event()

    async def runner(q, j):
        started.set()
        await asyncio.sleep(60)

    q = DownloadQueue(runner, workers=1)
    q.start()
    q.enqueue(job("job-1"))
    q.enqueue(job("job-2"))  # waits behind job-1
    await started.wait()

    assert q.cancel("job-2") is True  # queued
    assert q.cancel("job-1") is True  # running
    await wait_for(lambda: all(s["status"] == "error" for s in q.list_jobs()))
    assert {s["message"] for s in q.list_jobs()} == {"Cancelled"}
    assert q.cancel("job-1") is False and q.cancel("nope") is False
    await q.stop()


async def test_runner_exception_does_not_kill_worker():
    async def runner(q, j):
        if j.id == "job-1":
            raise RuntimeError("boom")
        q.set_status(j.id, "done", 100)

    q = DownloadQueue(runner, workers=1)
    q.start()
    q.enqueue(job("job-1"))
    q.enqueue(job("job-2"))
    await wait_for(lambda: len(q.list_jobs()) == 2 and q.list_jobs()[1]["status"] == "done")
    assert q.list_jobs()[0]["message"] == "Unexpected error: boom"
    await q.stop()


async def test_stop_cancels_in_flight_work():
    async def runner(q, j):
        await asyncio.sleep(60)

    q = DownloadQueue(runner, workers=2)
    q.start()
    q.enqueue(job("job-1"))
    await asyncio.sleep(0.05)
    await asyncio.wait_for(q.stop(), 2)
