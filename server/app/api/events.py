from __future__ import annotations

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..deps import EventBusDep
from ..events import EventBus

router = APIRouter()

KEEPALIVE = 15.0  # seconds between comment lines when nothing happens


@router.get("/events")
async def event_stream(event_bus: EventBusDep):
    """Server-Sent Events. Every message is {"type", "id", "data"}, where data is
    the whole resource as its REST endpoint returns it. Types: download.updated,
    book.updated. There is no replay: clients reload their snapshot whenever
    the stream (re)opens."""
    return StreamingResponse(_messages(event_bus), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _messages(event_bus: EventBus) -> AsyncIterator[str]:
    with event_bus.subscribe() as subscription:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(subscription.next(), KEEPALIVE)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # keeps proxies from closing an idle stream
                continue
            yield event.sse()
