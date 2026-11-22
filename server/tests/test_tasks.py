import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from opentelemetry import context as otel_context
from pydantic import BaseModel

from app.repositories import tasks as repo
from app.services.task_queue import TaskQueueService
from app.services.task_worker import TaskWorkerService
from app.tasks.base import BaseTask, TaskDeferred, TaskFailed
from app.tasks.signals import TaskSignals


class Payload(BaseModel):
    n: int = 0


class Once(BaseTask[Payload]):  # a throwaway task type: one attempt
    name = "once"


class Retrying(BaseTask[Payload]):  # three attempts
    name = "retrying"
    max_attempts = 3


@pytest.fixture
async def make(db):
    """Build a (queue, worker) pair; workers are stopped when the test ends."""
    built = []

    def _make(workers=1, **kw):
        signals = TaskSignals()
        kw.setdefault("cancel_poll", 0.02)
        kw.setdefault("retry_base_delay", 0)  # retry at once; backoff has its own tests
        worker = TaskWorkerService(db, signals, workers, **kw)
        built.append(worker)
        return TaskQueueService(db, signals), worker

    yield _make
    for w in built:
        await w.stop()


async def wait_for(predicate, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.01)


def status(db, task_id):
    return db.scalar("SELECT status FROM tasks WHERE id = ?", (task_id,))


def row(db, task_id):
    return db.query_one("SELECT status, attempts, error FROM tasks WHERE id = ?", (task_id,))


# --- ordering and claiming ---------------------------------------------------

async def test_tasks_run_in_the_order_they_were_queued(db, make):
    queue, worker = make()
    order = []

    async def handler(p, ctx):
        order.append(p.n)

    worker.register(Once, handler)
    for n in (3, 1, 2):  # queued in one burst, before any worker runs
        queue.enqueue(Once(payload=Payload(n=n)))
    worker.start()
    await wait_for(lambda: len(order) == 3)
    assert order == [3, 1, 2]


def test_two_workers_never_claim_the_same_task(db):
    with db.session() as s:
        for i in range(40):
            repo.add(s, id=f"t{i}", type="once", payload="{}")

    def drain():
        got = []
        while True:
            with db.session() as s:
                task = repo.claim_next(s)
            if task is None:
                return got
            got.append(task.id)

    with ThreadPoolExecutor(4) as pool:
        results = [f.result() for f in [pool.submit(drain) for _ in range(4)]]
    claimed = [i for r in results for i in r]
    assert sorted(claimed) == sorted(f"t{i}" for i in range(40))  # each exactly once


async def test_two_workers_run_each_task_once(db, make):
    queue, worker = make(workers=2)
    ran = []

    async def handler(p, ctx):
        ran.append(p.n)
        await asyncio.sleep(0.01)

    worker.register(Once, handler)
    for n in range(8):
        queue.enqueue(Once(payload=Payload(n=n)))
    worker.start()
    await wait_for(lambda: len(ran) == 8)
    await asyncio.sleep(0.1)
    assert sorted(ran) == list(range(8))


# --- failures and retries ----------------------------------------------------

async def test_failing_task_is_retried_until_max_attempts_then_fails(db, make):
    queue, worker = make()
    attempts = []

    async def handler(p, ctx):
        attempts.append(ctx.attempt)
        raise RuntimeError("boom")

    worker.register(Retrying, handler)
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "failed")
    assert attempts == [1, 2, 3]
    r = row(db, task_id)
    assert r["attempts"] == 3 and "boom" in r["error"]


async def test_permanent_failure_is_not_retried(db, make):
    queue, worker = make()
    calls = []

    async def handler(p, ctx):
        calls.append(ctx.attempt)
        raise TaskFailed("no good")

    worker.register(Retrying, handler)  # three attempts allowed, none used after TaskFailed
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "failed")
    await asyncio.sleep(0.1)
    assert calls == [1] and row(db, task_id)["error"] == "no good"


async def test_task_failed_with_retry_runs_again(db, make):
    queue, worker = make()

    async def handler(p, ctx):
        if ctx.attempt == 1:
            raise TaskFailed("try again", retry=True)

    worker.register(Retrying, handler)
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "completed")
    assert row(db, task_id)["attempts"] == 2


async def test_retries_wait_longer_each_time(db, make):
    queue, worker = make(retry_base_delay=10)
    assert 8 <= worker.retry_delay(1) <= 12 and 32 <= worker.retry_delay(2) <= 48  # 4x each time, +-20%
    calls = []

    async def handler(p, ctx):
        calls.append(ctx.attempt)
        raise RuntimeError("network down")

    worker.register(Retrying, handler)
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await wait_for(lambda: calls == [1] and status(db, task_id) == "pending")
    await asyncio.sleep(0.2)
    not_before = db.scalar("SELECT not_before FROM tasks WHERE id = ?", (task_id,))
    assert calls == [1] and not_before > repo.later(7)  # not retried at once: about 10 s from now


async def test_a_task_is_not_claimed_before_its_not_before(db):
    with db.session() as s:
        repo.add(s, id="t1", type="once", payload="{}")
    db.execute("UPDATE tasks SET not_before = ? WHERE id = 't1'", (repo.later(60),))
    with db.session() as s:
        assert repo.claim_next(s) is None
    db.execute("UPDATE tasks SET not_before = ? WHERE id = 't1'", (repo.now(),))
    with db.session() as s:
        assert repo.claim_next(s).id == "t1"


async def test_a_deferred_task_runs_later_without_using_up_an_attempt(db, make):
    queue, worker = make(idle_poll=0.05)
    runs = []

    async def handler(p, ctx):
        runs.append((ctx.attempt, time.monotonic()))
        if len(runs) < 3:
            raise TaskDeferred("not yet", 0.2)

    worker.register(Once, handler)  # one attempt allowed: deferring mustn't spend it
    task_id = queue.enqueue(Once(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "completed")
    assert [attempt for attempt, _ in runs] == [1, 1, 1]
    assert runs[1][1] - runs[0][1] >= 0.2 and runs[2][1] - runs[1][1] >= 0.2


async def test_handler_exception_does_not_kill_the_worker(db, make):
    queue, worker = make()

    async def handler(p, ctx):
        if p.n == 1:
            raise RuntimeError("boom")

    worker.register(Once, handler)
    first = queue.enqueue(Once(payload=Payload(n=1)))
    second = queue.enqueue(Once(payload=Payload(n=2)))
    worker.start()
    await wait_for(lambda: status(db, second) == "completed")
    assert status(db, first) == "failed"


async def test_unknown_type_and_invalid_payload_fail_permanently(db, make):
    _, worker = make()

    async def handler(p, ctx):
        pass

    worker.register(Retrying, handler)
    with db.session() as s:
        repo.add(s, id="u", type="mystery", payload="{}", max_attempts=3)
        repo.add(s, id="v", type="retrying", payload='{"n": "x"}', max_attempts=3)
    worker.start()
    await wait_for(lambda: status(db, "u") == "failed" and status(db, "v") == "failed")
    assert "Unknown task type" in row(db, "u")["error"] and row(db, "u")["attempts"] == 1
    assert "Invalid payload" in row(db, "v")["error"] and row(db, "v")["attempts"] == 1


# --- cancelling --------------------------------------------------------------

async def test_cancelled_pending_task_never_runs(db, make):
    queue, worker = make()
    calls = []

    async def handler(p, ctx):
        calls.append(1)

    worker.register(Once, handler)
    task_id = queue.enqueue(Once(payload=Payload()))
    assert queue.cancel(task_id) is True
    worker.start()
    await asyncio.sleep(0.1)
    assert calls == [] and status(db, task_id) == "cancelled"
    assert queue.cancel(task_id) is False and queue.cancel("nope") is False


@pytest.mark.parametrize("through_the_queue", [True, False])
async def test_cancelling_a_running_task_stops_its_handler(db, make, through_the_queue):
    queue, worker = make()
    started, stopped, calls = asyncio.Event(), asyncio.Event(), []

    async def handler(p, ctx):
        calls.append(ctx.attempt)
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            stopped.set()
            raise

    worker.register(Retrying, handler)  # three attempts: a cancel must not be retried
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await asyncio.wait_for(started.wait(), 3)
    if through_the_queue:
        assert queue.cancel(task_id) is True  # stops it at once, through the signals
    else:
        with db.session() as s:  # as another process would: only the row changes
            assert repo.cancel(s, task_id)
    await asyncio.wait_for(stopped.wait(), 3)  # the watcher notices the row
    await asyncio.sleep(0.1)
    assert status(db, task_id) == "cancelled" and calls == [1]


# --- restarts ----------------------------------------------------------------

async def test_interrupted_task_is_released_at_startup_without_losing_an_attempt(db, make):
    queue, worker = make()
    task_id = queue.enqueue(Once(payload=Payload()))  # one attempt allowed
    with db.session() as s:
        assert repo.claim_next(s).id == task_id  # claimed, then the app died
    assert row(db, task_id)["status"] == "processing" and row(db, task_id)["attempts"] == 1
    seen = []

    async def handler(p, ctx):
        seen.append((ctx.attempt, ctx.max_attempts))

    worker.register(Once, handler)
    worker.start()
    await wait_for(lambda: status(db, task_id) == "completed")
    assert seen == [(1, 1)]  # it ran, as attempt 1


async def test_stop_cancels_in_flight_work_and_the_task_resumes_next_start(db, make):
    queue, worker = make(workers=2)
    started, stopped = asyncio.Event(), asyncio.Event()

    async def slow(p, ctx):
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            stopped.set()
            raise

    worker.register(Once, slow)
    task_id = queue.enqueue(Once(payload=Payload()))
    worker.start()
    await asyncio.wait_for(started.wait(), 3)
    await asyncio.wait_for(worker.stop(), 2)
    assert stopped.is_set()
    assert status(db, task_id) == "processing"  # left for the next startup

    _, again = make()

    async def fast(p, ctx):
        pass

    again.register(Once, fast)
    again.start()
    await wait_for(lambda: status(db, task_id) == "completed")


async def test_old_finished_tasks_are_pruned_at_startup(db, make):
    with db.session() as s:
        for i in range(4):
            repo.add(s, id=f"t{i}", type="once", payload="{}")
    for _ in range(4):
        with db.session() as s:
            repo.complete(s, repo.claim_next(s).id)
    _, worker = make(history_limit=2)
    worker.start()
    assert {r["id"] for r in db.query("SELECT id FROM tasks")} == {"t2", "t3"}  # the newest two


# --- waking, heartbeat, tracing ------------------------------------------------

async def test_enqueue_wakes_an_idle_worker(db, make):
    queue, worker = make(idle_poll=30)  # without a wake-up it would sleep for 30 s
    done = []

    async def handler(p, ctx):
        done.append(1)

    worker.register(Once, handler)
    worker.start()
    await asyncio.sleep(0.1)  # the worker is idle now
    queue.enqueue(Once(payload=Payload()))
    await wait_for(lambda: done, timeout=2)


async def test_enqueue_in_a_callers_transaction_wakes_workers_after_the_commit(db, make):
    queue, worker = make(idle_poll=30)
    done = []

    async def handler(p, ctx):
        done.append(1)

    worker.register(Once, handler)
    worker.start()
    await asyncio.sleep(0.1)
    with db.session() as s:
        queue.enqueue(Once(payload=Payload()), session=s)
        await asyncio.sleep(0.1)
        assert not done  # not visible, not woken, before the commit
    await wait_for(lambda: done, timeout=2)


def test_enqueue_in_a_callers_transaction_is_rolled_back_with_it(db):
    queue = TaskQueueService(db, TaskSignals())
    with pytest.raises(RuntimeError):
        with db.session() as s:
            queue.enqueue(Once(payload=Payload()), session=s)
            raise RuntimeError("the caller's own write failed")
    assert db.scalar("SELECT COUNT(*) FROM tasks") == 0


async def test_locked_at_is_refreshed_while_a_handler_runs(db, make):
    queue, worker = make(heartbeat_interval=0.05)
    release = asyncio.Event()

    async def handler(p, ctx):
        await release.wait()

    worker.register(Once, handler)
    task_id = queue.enqueue(Once(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "processing")
    first = db.scalar("SELECT locked_at FROM tasks WHERE id = ?", (task_id,))
    await wait_for(lambda: db.scalar("SELECT locked_at FROM tasks WHERE id = ?", (task_id,)) != first)
    release.set()


async def test_handler_runs_in_the_trace_context_of_the_enqueuer(db, make):
    queue, worker = make()
    seen = []

    async def handler(p, ctx):
        seen.append(otel_context.get_value("test-key"))

    worker.register(Once, handler)
    token = otel_context.attach(otel_context.set_value("test-key", "from-the-request"))
    try:
        queue.enqueue(Once(payload=Payload()))
    finally:
        otel_context.detach(token)
    worker.start()
    await wait_for(lambda: seen)
    assert seen == ["from-the-request"]


# --- wiring --------------------------------------------------------------------

def test_app_runs_tasks_registered_on_its_worker(client):
    ctx = client.app.state.ctx
    ran = []

    async def handler(p, c):
        ran.append(p.n)

    ctx.task_worker.register(Once, handler)
    ctx.task_queue.enqueue(Once(payload=Payload(n=7)))  # from this thread; the app's loop runs the handler
    end = time.monotonic() + 3
    while not ran and time.monotonic() < end:
        time.sleep(0.01)
    assert ran == [7]
