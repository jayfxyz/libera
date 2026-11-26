# Task queue: mental model

Background work (downloads today) runs through a small database-backed queue.
Workers **pull** from the `tasks` table; nothing pushes work to them.

```
 producers                 STORE                       consumers
 ─────────                 ─────                       ─────────
 DownloadsService ──►  TaskQueueService  ◄── claim ──  TaskWorker ×N (one per task_type)
                       (tasks table)                        │
                                                            │ prepare(type, payload)
                                                            ▼
                                                       TaskRegistry ──► handler fn
                                                       {type → handler}

 TaskSignals: in-process side channel (wake idle workers, cancel a running handler).
              An optional accelerator. The table is the source of truth.
```

## Components

### `TaskQueueService` (`server/app/services/task_queue.py`)

The store and the producer API: the only thing that talks to the `tasks` table.

```python
class TaskQueueService:
    # producer side
    enqueue(task, session=None) -> task_id   # insert row, then nudge workers
                                             # (after commit, if given a session)
    cancel(task_id) -> bool                  # mark cancelled; stop the handler if it runs here

    # worker side
    recover(known_types)                     # startup: processing -> pending, fail pending tasks of a
                                             # type with no handler, prune old finished
    claim(task_type) -> Task | None          # atomically pending -> processing
    heartbeat(id) / is_processing(id)        # "am I still wanted?"
    complete(id)
    fail(id, error, retry, retry_delay)      # -> pending (retry) or failed
    defer(id, reason, delay)                 # -> pending, attempt not spent
```

### `TaskRegistry` (`server/app/tasks/registry.py`)

Maps a task type to its handler.

```python
class TaskRegistry:
    add(task_cls, handler)
    prepare(task_type, payload_json) -> (handler, validated_payload)  # TaskFailed if unknown/invalid
```

### `TaskWorker` (`server/app/services/task_worker.py`)

Claims and runs tasks of one type, `concurrency` at a time.

```python
class TaskWorker:
    __init__(queue, registry, signals, task_type, concurrency)
    start()    # spawn `concurrency` loops
    stop()     # cancel the loops (and their in-flight handlers)
```

The loop:

```python
loop:
    task = queue.claim(task_type)
    if not task:
        sleep until woken or idle_poll
        continue

    handler, payload = registry.prepare(task.type, task.payload)

    run handler(payload, ctx) alongside a monitor:
        monitor: every ~1s  -> queue.is_processing(id)? else cancel the handler
                 every ~30s -> queue.heartbeat(id)

    outcome:
        returns                 -> queue.complete(id)
        raises TaskFailed       -> queue.fail(id, retry=e.retry)
        raises TaskDeferred     -> queue.defer(id, delay)
        raises anything else    -> queue.fail(id, retry=True)   # backoff 4x per attempt
        cancelled via the row   -> nothing; the row already says so
        worker stopped          -> stays `processing`; recover() releases it next start
```

### The handler contract

```python
async def handler(payload, ctx: TaskContext) -> None
# raise TaskFailed(msg, retry=False)   permanent (retry=True to retry while attempts remain)
# raise TaskDeferred(msg, delay)       try again later, without using up an attempt
```

### `TaskSignals` (`server/app/tasks/signals.py`)

In-process only: wake events per task type, a way to cancel a running handler,
and the enqueuer's trace context. A separate worker process would not share
it and would fall back to the table (idle polling, the monitor's row check).

## Wiring (`server/app/main.py`)

```python
registry.add(DownloadBook, handlers.download_book)
registry.add(DecryptBook,  handlers.decrypt_book)

workers = [TaskWorker(task_type="download_book", concurrency=config.download_workers),
           TaskWorker(task_type="decrypt_book",  concurrency=1)]

queue.recover(known_types=registry.types)
for w in workers: w.start()
```

## Dependencies

```
TaskWorker ──► TaskQueueService, TaskRegistry, TaskSignals
TaskQueueService ──► repository (SQL), TaskSignals
TaskRegistry ──► (nothing)
DownloadHandlers ──► DownloadsService ──► TaskQueueService   # a handler can enqueue the next task
```

The last link is how `download_book` ends by enqueueing `decrypt_book`
(`DownloadsService.chain_decrypt`).
