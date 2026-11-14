"""In-process side channel between enqueue and workers.

Everything here is a best-effort accelerator: the tasks table is the source of
truth. A separate worker process would not share one of these, and would fall
back to the table (idle polling, and the worker's check for a cancelled row).
"""

import asyncio
from typing import Any


class TaskSignals:
    def __init__(self) -> None:
        self.wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._traces: dict[str, Any] = {}  # trace context of tasks enqueued in this process
        self._running: dict[str, asyncio.Task] = {}  # handlers running in this process

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _call(self, fn, *args) -> None:
        """Run fn on the event loop, from any thread. No-op before attach / after the loop closed."""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(fn, *args)

    def nudge(self) -> None:
        """Something was enqueued: wake idle workers."""
        self._call(self.wake.set)

    def request_cancel(self, task_id: str) -> None:
        """Cancel the handler of a running task now, if it runs in this process."""
        self._call(self._cancel, task_id)

    def _cancel(self, task_id: str) -> None:
        if task := self._running.get(task_id):
            task.cancel()

    def set_running(self, task_id: str, task: asyncio.Task | None) -> None:
        if task is None:
            self._running.pop(task_id, None)
        else:
            self._running[task_id] = task

    def remember_trace(self, task_id: str, context: Any) -> None:
        self._traces[task_id] = context

    def trace_for(self, task_id: str) -> Any:
        return self._traces.get(task_id)

    def forget(self, task_id: str) -> None:
        self._traces.pop(task_id, None)
