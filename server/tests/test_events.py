"""The event bus, and GET /api/events served by a real uvicorn server (Starlette's
TestClient waits for a response to end, so it can't read an endless stream)."""

import asyncio
import json
import threading
import time

import httpx
import pytest
import uvicorn

from app.api import events as events_api
from app.events import EventBus
from app.main import create_app
from tests.conftest import add_account, import_books, make_book


# --- the bus ----------------------------------------------------------------------------

@pytest.fixture
async def bus():
    b = EventBus()
    b.attach(asyncio.get_running_loop())
    return b


async def read_all(subscription, timeout=0.1):
    """Every event waiting for this subscription."""
    events = []
    while True:
        try:
            events.append(await asyncio.wait_for(subscription.next(), timeout))
        except asyncio.TimeoutError:
            return events


async def test_a_subscription_keeps_only_the_latest_event_per_resource(bus):
    with bus.subscribe() as sub:
        for pct in (10, 20, 30):
            bus.publish("download.updated", "d1", {"percent": pct})
        bus.publish("download.updated", "d2", {"percent": 5})
        bus.publish("book.updated", "d1", {"title": "same id, other type"})
        events = await read_all(sub)
    assert [(e.type, e.id, e.data) for e in events] == [
        ("download.updated", "d1", {"percent": 30}),
        ("download.updated", "d2", {"percent": 5}),
        ("book.updated", "d1", {"title": "same id, other type"}),
    ]


async def test_a_reader_that_fell_behind_still_gets_the_final_state(bus):
    with bus.subscribe() as sub:
        for pct in range(1000):  # far more than any buffer, while nobody reads
            bus.publish("download.updated", "d1", {"status": "downloading", "percent": pct})
        bus.publish("download.updated", "d1", {"status": "done", "percent": 100})
        events = await read_all(sub)
    assert [e.data for e in events] == [{"status": "done", "percent": 100}]


async def test_publish_is_safe_from_another_thread(bus):
    with bus.subscribe() as sub:
        await asyncio.to_thread(bus.publish, "download.updated", "d1", {"status": "done"})
        event = await asyncio.wait_for(sub.next(), 1)
    assert (event.type, event.id, event.data) == ("download.updated", "d1", {"status": "done"})


async def test_events_go_to_every_subscriber_and_stop_after_unsubscribing(bus):
    with bus.subscribe() as first, bus.subscribe() as second:
        bus.publish("download.updated", "d1", {"n": 1})
        assert [e.data for e in await read_all(first)] == [{"n": 1}]
        assert [e.data for e in await read_all(second)] == [{"n": 1}]
    bus.publish("download.updated", "d1", {"n": 2})  # nobody listening: dropped
    assert await read_all(first) == []


def test_an_event_is_one_sse_message_with_the_envelope():
    from app.events import Event
    message = Event("download.updated", "d1", {"id": "d1", "title": "Ünïcode\nnewline"}).sse()
    assert message.startswith("data: ") and message.endswith("\n\n") and message.count("\n") == 2
    assert json.loads(message[len("data: "):]) == {
        "type": "download.updated", "id": "d1", "data": {"id": "d1", "title": "Ünïcode\nnewline"}}


# --- the endpoint, over a real HTTP server ---------------------------------------------------

@pytest.fixture
def server(config, db, pipeline, monkeypatch):
    monkeypatch.setattr(events_api, "KEEPALIVE", 0.2)  # so a waiting reader wakes up often
    app = create_app(config, db, pipeline=pipeline)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning",
                                        timeout_graceful_shutdown=1))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not srv.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.01)
    port = srv.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(5)


def read_events(lines, until, timeout=5.0):
    """Parse SSE lines into envelopes until until(events) is true."""
    events, deadline = [], time.monotonic() + timeout
    for line in lines:
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
            if until(events):
                return events
        assert time.monotonic() < deadline, f"timed out; got {events}"
    raise AssertionError("stream ended")


def test_the_stream_delivers_download_and_book_updates(server, db):
    add_account(db)
    import_books(db, 1, [make_book("B1", title="The Book", authors=["Jane Author"])])
    book_id = db.scalar("SELECT id FROM books")

    def finished(events):
        done = any(e["type"] == "download.updated" and e["data"]["status"] == "done" for e in events)
        return done and any(e["type"] == "book.updated" for e in events)

    with httpx.Client(base_url=server, timeout=10) as http:
        with http.stream("GET", "/api/events", headers={"Accept-Encoding": "gzip"}) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers["cache-control"] == "no-cache"
            assert "content-encoding" not in resp.headers  # compression would hold events back
            lines = resp.iter_lines()
            assert next(lines) == ": connected"
            download_id = httpx.post(f"{server}/api/downloads", json={"book_id": book_id}).json()["id"]
            events = read_events(lines, finished)

    download = [e for e in events if e["type"] == "download.updated"][-1]
    assert download["id"] == download_id and download["data"]["id"] == download_id
    assert download["data"] == httpx.get(f"{server}/api/downloads").json()[0]  # the same shape as REST
    book = next(e for e in events if e["type"] == "book.updated")
    assert (book["id"], book["data"]["id"], book["data"]["liberation_status"]) == (str(book_id), book_id, "liberated")
    assert book["data"]["updated_at"]


def test_an_idle_stream_sends_keep_alive_comments(server):
    with httpx.Client(base_url=server, timeout=5) as http:
        with http.stream("GET", "/api/events") as resp:
            lines = resp.iter_lines()
            assert next(lines) == ": connected"
            assert ": keep-alive" in [next(lines) for _ in range(4)]  # blank separators in between
