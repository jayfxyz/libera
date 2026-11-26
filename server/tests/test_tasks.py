import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from opentelemetry import context as otel_context
from pydantic import BaseModel

from app.repositories import tasks as repo
from app.services.task_queue import TaskQueueService
from app.services.task_worker import TaskWorker
from app.tasks.base import BaseTask, TaskDeferred, TaskFailed
from app.tasks.registry import TaskRegistry
from app.tasks.signals import TaskSignals


class Payload(BaseModel):
    n: int = 0


class Once(BaseTask[Payload]):  # a throwaway task type: one attempt
    name = "once"


class Retrying(BaseTask[Payload]):  # three attempts
    name = "retrying"
    max_attempts = 3


class Dedicated(BaseTask[Payload]):  # a task type with its own worker pool
    name = "dedicated"


class Rig:
    """A queue and a registry, and the workers built on them."""

    def __init__(self, db, **worker_kw):
        self.signals = TaskSignals()
        self.queue = TaskQueueService(db, self.signals)
        self.registry = TaskRegistry()
        self.workers: list[TaskWorker] = []
        self._worker_kw = worker_kw

    def worker(self, task_cls, handler, *, concurrency=1) -> TaskWorker:
        """Register `handler` for the task type and build (not start) a worker for it."""
        self.registry.add(task_cls, handler)
        return self.add_worker(task_cls.name, concurrency=concurrency)

    def add_worker(self, task_type, *, concurrency=1) -> TaskWorker:
        worker = TaskWorker(queue=self.queue, registry=self.registry, signals=self.signals,
                            task_type=task_type, concurrency=concurrency, **self._worker_kw)
        self.workers.append(worker)
        return worker


@pytest.fixture
async def make(db):
    """Build a Rig; its workers are stopped when the test ends."""
    built = []

    def _make(**kw):
        kw.setdefault("cancel_poll", 0.02)
        kw.setdefault("retry_base_delay", 0)  # retry at once; backoff has its own tests
        built.append(Rig(db, **kw))
        return built[-1]

    yield _make
    for rig in built:
        for w in rig.workers:
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
    rig = make()
    queue = rig.queue
    order = []

    async def handler(p, ctx):
        order.append(p.n)

    worker = rig.worker(Once, handler)
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
    rig = make()
    queue = rig.queue
    ran = []

    async def handler(p, ctx):
        ran.append(p.n)
        await asyncio.sleep(0.01)

    worker = rig.worker(Once, handler, concurrency=2)
    for n in range(8):
        queue.enqueue(Once(payload=Payload(n=n)))
    worker.start()
    await wait_for(lambda: len(ran) == 8)
    await asyncio.sleep(0.1)
    assert sorted(ran) == list(range(8))


async def test_dedicated_pool_limits_concurrency_and_wakes_independently(db, make):
    rig = make(idle_poll=30)
    queue = rig.queue
    in_flight, max_in_flight, ran = 0, 0, []
    once_blocked = asyncio.Event()
    once_started = asyncio.Event()

    async def slow_once(p, ctx):
        once_started.set()
        await once_blocked.wait()

    async def serial(p, ctx):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.03)
        ran.append(p.n)
        in_flight -= 1

    rig.worker(Once, slow_once, concurrency=3).start()
    rig.worker(Dedicated, serial, concurrency=1).start()
    await asyncio.sleep(0.05)  # all workers idle

    # Saturate the Once pool: Dedicated tasks must still start immediately, one at a time.
    for n in range(3):
        queue.enqueue(Once(payload=Payload(n=n)))
    await asyncio.wait_for(once_started.wait(), 2)
    for n in range(4):
        queue.enqueue(Dedicated(payload=Payload(n=n)))
    await wait_for(lambda: len(ran) == 4, timeout=2)
    assert max_in_flight == 1 and ran == [0, 1, 2, 3]
    once_blocked.set()


# --- failures and retries ----------------------------------------------------

async def test_failing_task_is_retried_until_max_attempts_then_fails(db, make):
    rig = make()
    queue = rig.queue
    attempts = []

    async def handler(p, ctx):
        attempts.append(ctx.attempt)
        raise RuntimeError("boom")

    worker = rig.worker(Retrying, handler)
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "failed")
    assert attempts == [1, 2, 3]
    r = row(db, task_id)
    assert r["attempts"] == 3 and "boom" in r["error"]


async def test_permanent_failure_is_not_retried(db, make):
    rig = make()
    queue = rig.queue
    calls = []

    async def handler(p, ctx):
        calls.append(ctx.attempt)
        raise TaskFailed("no good")

    worker = rig.worker(Retrying, handler)  # three attempts allowed, none used after TaskFailed
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "failed")
    await asyncio.sleep(0.1)
    assert calls == [1] and row(db, task_id)["error"] == "no good"


async def test_task_failed_with_retry_runs_again(db, make):
    rig = make()
    queue = rig.queue

    async def handler(p, ctx):
        if ctx.attempt == 1:
            raise TaskFailed("try again", retry=True)

    worker = rig.worker(Retrying, handler)
    task_id = queue.enqueue(Retrying(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "completed")
    assert row(db, task_id)["attempts"] == 2


async def test_retries_wait_longer_each_time(db, make):
    rig = make(retry_base_delay=10)
    queue = rig.queue
    calls = []

    async def handler(p, ctx):
        calls.append(ctx.attempt)
        raise RuntimeError("network down")

    worker = rig.worker(Retrying, handler)
    assert 8 <= worker.retry_delay(1) <= 12 and 32 <= worker.retry_delay(2) <= 48  # 4x each time, +-20%
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
    rig = make(idle_poll=0.05)
    queue = rig.queue
    runs = []

    async def handler(p, ctx):
        runs.append((ctx.attempt, time.monotonic()))
        if len(runs) < 3:
            raise TaskDeferred("not yet", 0.2)

    worker = rig.worker(Once, handler)  # one attempt allowed: deferring mustn't spend it
    task_id = queue.enqueue(Once(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "completed")
    assert [attempt for attempt, _ in runs] == [1, 1, 1]
    assert runs[1][1] - runs[0][1] >= 0.2 and runs[2][1] - runs[1][1] >= 0.2


async def test_handler_exception_does_not_kill_the_worker(db, make):
    rig = make()
    queue = rig.queue

    async def handler(p, ctx):
        if p.n == 1:
            raise RuntimeError("boom")

    worker = rig.worker(Once, handler)
    first = queue.enqueue(Once(payload=Payload(n=1)))
    second = queue.enqueue(Once(payload=Payload(n=2)))
    worker.start()
    await wait_for(lambda: status(db, second) == "completed")
    assert status(db, first) == "failed"


async def test_unknown_type_and_invalid_payload_fail_permanently(db, make):
    rig = make()

    async def handler(p, ctx):
        pass

    retrying = rig.worker(Retrying, handler)
    mystery = rig.add_worker("mystery")  # a type the registry has no handler for
    with db.session() as s:
        repo.add(s, id="u", type="mystery", payload="{}", max_attempts=3)
        repo.add(s, id="v", type="retrying", payload='{"n": "x"}', max_attempts=3)
    assert await mystery.process() and await retrying.process()
    assert status(db, "u") == "failed" and status(db, "v") == "failed"
    assert "Unknown task type" in row(db, "u")["error"] and row(db, "u")["attempts"] == 1
    assert "Invalid payload" in row(db, "v")["error"] and row(db, "v")["attempts"] == 1


# --- cancelling --------------------------------------------------------------

async def test_cancelled_pending_task_never_runs(db, make):
    rig = make()
    queue = rig.queue
    calls = []

    async def handler(p, ctx):
        calls.append(1)

    worker = rig.worker(Once, handler)
    task_id = queue.enqueue(Once(payload=Payload()))
    assert queue.cancel(task_id) is True
    worker.start()
    await asyncio.sleep(0.1)
    assert calls == [] and status(db, task_id) == "cancelled"
    assert queue.cancel(task_id) is False and queue.cancel("nope") is False


@pytest.mark.parametrize("through_the_queue", [True, False])
async def test_cancelling_a_running_task_stops_its_handler(db, make, through_the_queue):
    rig = make()
    queue = rig.queue
    started, stopped, calls = asyncio.Event(), asyncio.Event(), []

    async def handler(p, ctx):
        calls.append(ctx.attempt)
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            stopped.set()
            raise

    worker = rig.worker(Retrying, handler)  # three attempts: a cancel must not be retried
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
    rig = make()
    queue = rig.queue
    task_id = queue.enqueue(Once(payload=Payload()))  # one attempt allowed
    with db.session() as s:
        assert repo.claim_next(s).id == task_id  # claimed, then the app died
    assert row(db, task_id)["status"] == "processing" and row(db, task_id)["attempts"] == 1
    seen = []

    async def handler(p, ctx):
        seen.append((ctx.attempt, ctx.max_attempts))

    worker = rig.worker(Once, handler)
    queue.recover(known_types=rig.registry.types)  # as at app startup
    worker.start()
    await wait_for(lambda: status(db, task_id) == "completed")
    assert seen == [(1, 1)]  # it ran, as attempt 1


async def test_stop_cancels_in_flight_work_and_the_task_resumes_next_start(db, make):
    rig = make()
    queue = rig.queue
    started, stopped = asyncio.Event(), asyncio.Event()

    async def slow(p, ctx):
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            stopped.set()
            raise

    worker = rig.worker(Once, slow, concurrency=2)
    task_id = queue.enqueue(Once(payload=Payload()))
    worker.start()
    await asyncio.wait_for(started.wait(), 3)
    await asyncio.sleep(0.1)  # the other loop's claim (a thread, which stop() can't cancel) is over: nothing left to claim
    await asyncio.wait_for(worker.stop(), 2)
    assert stopped.is_set()
    assert status(db, task_id) == "processing"  # left for the next startup

    again = make()

    async def fast(p, ctx):
        pass

    worker = again.worker(Once, fast)
    again.queue.recover(known_types=again.registry.types)  # as at app startup
    worker.start()
    await wait_for(lambda: status(db, task_id) == "completed")


async def test_pending_tasks_of_a_type_with_no_handler_are_failed_at_startup(db, make):
    rig = make()

    async def handler(p, ctx):
        pass

    rig.worker(Once, handler)
    with db.session() as s:
        repo.add(s, id="known", type="once", payload="{}")
        repo.add(s, id="stray", type="mystery", payload="{}")
    rig.queue.recover(known_types=rig.registry.types)
    assert status(db, "stray") == "failed" and "Unknown task type: mystery" in row(db, "stray")["error"]
    assert status(db, "known") == "pending"


async def test_old_finished_tasks_are_pruned_at_startup(db, make):
    with db.session() as s:
        for i in range(4):
            repo.add(s, id=f"t{i}", type="once", payload="{}")
    for _ in range(4):
        with db.session() as s:
            repo.complete(s, repo.claim_next(s).id)
    rig = make()
    rig.queue.recover(known_types=rig.registry.types, history_limit=2)
    assert {r["id"] for r in db.query("SELECT id FROM tasks")} == {"t2", "t3"}  # the newest two


# --- waking, heartbeat, tracing ------------------------------------------------

async def test_enqueue_wakes_an_idle_worker(db, make):
    rig = make(idle_poll=30)  # without a wake-up it would sleep for 30 s
    queue = rig.queue
    done = []

    async def handler(p, ctx):
        done.append(1)

    worker = rig.worker(Once, handler)
    worker.start()
    await asyncio.sleep(0.1)  # the worker is idle now
    queue.enqueue(Once(payload=Payload()))
    await wait_for(lambda: done, timeout=2)


async def test_enqueue_in_a_callers_transaction_wakes_workers_after_the_commit(db, make):
    rig = make(idle_poll=30)
    queue = rig.queue
    done = []

    async def handler(p, ctx):
        done.append(1)

    worker = rig.worker(Once, handler)
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
    rig = make(heartbeat_interval=0.05)
    queue = rig.queue
    release = asyncio.Event()

    async def handler(p, ctx):
        await release.wait()

    worker = rig.worker(Once, handler)
    task_id = queue.enqueue(Once(payload=Payload()))
    worker.start()
    await wait_for(lambda: status(db, task_id) == "processing")
    first = db.scalar("SELECT locked_at FROM tasks WHERE id = ?", (task_id,))
    await wait_for(lambda: db.scalar("SELECT locked_at FROM tasks WHERE id = ?", (task_id,)) != first)
    release.set()


async def test_handler_runs_in_the_trace_context_of_the_enqueuer(db, make):
    rig = make()
    queue = rig.queue
    seen = []

    async def handler(p, ctx):
        seen.append(otel_context.get_value("test-key"))

    worker = rig.worker(Once, handler)
    token = otel_context.attach(otel_context.set_value("test-key", "from-the-request"))
    try:
        queue.enqueue(Once(payload=Payload()))
    finally:
        otel_context.detach(token)
    worker.start()
    await wait_for(lambda: seen)
    assert seen == ["from-the-request"]


# --- wiring --------------------------------------------------------------------

def test_app_runs_the_download_tasks_on_workers_of_their_own(client):
    ctx = client.app.state.ctx
    assert sorted(w.task_type for w in ctx.task_workers) == ["decrypt_book", "download_book"]


def test_app_runs_tasks_of_a_registered_type_on_a_worker(client):
    ctx = client.app.state.ctx
    ran = []

    async def handler(p, c):
        ran.append(p.n)

    ctx.task_registry.add(Once, handler)
    worker = TaskWorker(queue=ctx.task_queue, registry=ctx.task_registry, signals=TaskSignals(),
                        task_type=Once.name, idle_poll=0.05)
    client.portal.call(worker.start)  # on the app's event loop
    try:
        ctx.task_queue.enqueue(Once(payload=Payload(n=7)))
        end = time.monotonic() + 3
        while not ran and time.monotonic() < end:
            time.sleep(0.01)
        assert ran == [7]
    finally:
        client.portal.call(worker.stop)
