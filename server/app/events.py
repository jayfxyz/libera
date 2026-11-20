"""In-process event bus: publishers announce that a resource changed, and every
open event stream receives the resource's latest state.

- publish() is safe to call from any thread.
- A subscription keeps only the latest event per (type, id): a slow reader
  skips intermediate states (a percentage) but never misses the final one.
- Best effort: the database is the source of truth, and clients reload their
  snapshot whenever their stream (re)opens. This interface is the seam where
  a real broker would go if workers ever ran in a separate process.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class Event:
    type: str  # e.g. "download.updated"
    id: str  # the resource's id
    data: dict[str, Any]  # the whole resource, as its REST endpoint returns it

    def sse(self) -> str:
        """One Server-Sent Events message."""
        body = json.dumps({"type": self.type, "id": self.id, "data": self.data}, ensure_ascii=False)
        return f"data: {body}\n\n"


class Subscription:
    """The events one reader hasn't read yet: the latest per (type, id), in
    the order of their latest change."""

    def __init__(self) -> None:
        self._pending: dict[tuple[str, str], Event] = {}
        self._ready = asyncio.Event()

    def offer(self, event: Event) -> None:
        key = (event.type, event.id)
        self._pending.pop(key, None)  # re-insert: the newest change goes last
        self._pending[key] = event
        self._ready.set()

    async def next(self) -> Event:
        while not self._pending:
            self._ready.clear()
            await self._ready.wait()
        return self._pending.pop(next(iter(self._pending)))


class EventBus:
    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, type: str, id: str | int, data: dict[str, Any]) -> None:  # noqa: A002
        """Announce a resource's new state. No-op before attach or after the loop closed."""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._deliver, Event(type, str(id), data))

    def _deliver(self, event: Event) -> None:
        for subscription in list(self._subscriptions):
            subscription.offer(event)

    @contextmanager
    def subscribe(self) -> Iterator[Subscription]:
        subscription = Subscription()
        self._subscriptions.add(subscription)
        try:
            yield subscription
        finally:
            self._subscriptions.discard(subscription)
