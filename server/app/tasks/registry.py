"""Which handler runs which task type."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from .base import BaseTask, TaskContext, TaskFailed

Handler = Callable[[Any, TaskContext], Awaitable[None]]
"""`async def handler(payload, ctx: TaskContext) -> None`"""


class TaskRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[type[BaseTask], Handler]] = {}

    def add(self, task_cls: type[BaseTask], handler: Handler) -> None:
        self._entries[task_cls.name] = (task_cls, handler)

    def prepare(self, *, task_type: str, payload: str) -> tuple[Handler, BaseModel]:
        """The handler for a task type and its validated payload (given as JSON).
        TaskFailed if the type is unknown or the payload is not valid."""
        entry = self._entries.get(task_type)
        if entry is None:
            raise TaskFailed(f"Unknown task type: {task_type}")
        task_cls, handler = entry
        try:
            return handler, task_cls(payload=json.loads(payload)).payload
        except ValueError as e:  # bad JSON, or a payload the task's model rejects
            raise TaskFailed(f"Invalid payload: {e}") from e
