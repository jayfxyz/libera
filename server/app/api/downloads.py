from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import library
from ..config import FORMATS
from ..context import AppContext, get_ctx
from ..db import Database
from ..jobs.queue import DownloadJob
from ..telemetry import tracer

router = APIRouter()


class EnqueueRequest(BaseModel):
    book_id: int
    audible_id: str
    account_id: int
    format: str = ""
    split_chapters: bool = False


def _book_meta(db: Database, book_id: int, account_id: int) -> dict | None:
    row = db.query_one(
        """SELECT a.audible_account_id, b.title, COALESCE(b.language,'') AS language,
                  COALESCE(b.length_minutes,0) AS length_minutes, COALESCE(lb.date_added,'') AS date_added,
                  COALESCE(b.date_published,'') AS date_published
           FROM accounts a
           JOIN library_books lb ON lb.account_id = a.id
           JOIN books b ON b.id = lb.book_id
           WHERE a.id = ? AND b.id = ?""",
        (account_id, book_id),
    )
    if row is None:
        return None
    meta = dict(row)
    people = library.contributors(db, book_id)
    meta["authors"], meta["narrators"] = ", ".join(people["author"]), ", ".join(people["narrator"])
    series = db.query_one(
        """SELECT s.name, COALESCE(sb.book_index,'') AS idx FROM series s
           JOIN series_books sb ON sb.series_id = s.id WHERE sb.book_id = ? LIMIT 1""",
        (book_id,),
    )
    meta["series_name"], meta["series_index"] = (series["name"], series["idx"]) if series else ("", "")
    return meta


@router.post("/downloads", status_code=202)
async def enqueue_download(req: EnqueueRequest, ctx: AppContext = Depends(get_ctx)):
    fmt = req.format or ctx.config.default_format
    if fmt not in FORMATS:
        raise HTTPException(400, "format must be 'm4b' or 'mp3'")
    meta = await run_in_threadpool(_book_meta, ctx.db, req.book_id, req.account_id)
    if meta is None:
        raise HTTPException(404, "book not found for this account")

    # {year} is the publication year; fall back to when it joined the library.
    year = (meta["date_published"] or meta["date_added"])[:4]
    settings = ctx.config.snapshot()
    job = DownloadJob(
        id=f"dl-{req.book_id}-{int(time.time() * 1000)}",
        book_id=req.book_id,
        audible_id=req.audible_id,
        account_id=req.account_id,
        audible_account_id=meta["audible_account_id"],
        title=meta["title"],
        format=fmt,
        output_dir=settings.output_dir,
        filename_template=settings.filename_template,
        folder_template=settings.folder_template,
        authors=meta["authors"],
        narrators=meta["narrators"],
        series_name=meta["series_name"],
        series_index=meta["series_index"],
        language=meta["language"],
        year=year if len(year) == 4 else "",
        duration_h=str(meta["length_minutes"] // 60) if meta["length_minutes"] > 0 else "",
        split_chapters=req.split_chapters,
    )
    with tracer.start_as_current_span("job.enqueue", attributes={
        "job.id": job.id, "job.asin": job.audible_id, "job.format": job.format,
    }):
        ctx.queue.enqueue(job)
    return {"job_id": job.id}


@router.get("/downloads")
def list_downloads(ctx: AppContext = Depends(get_ctx)):
    return ctx.queue.list_jobs()


@router.delete("/downloads/{job_id}", status_code=204)
async def cancel_download(job_id: str, ctx: AppContext = Depends(get_ctx)):
    if not ctx.queue.cancel(job_id):
        raise HTTPException(404, "no running or queued download with that id")
    return Response(status_code=204)


async def download_progress(ws: WebSocket) -> None:
    """Stream download progress events to the browser."""
    ctx: AppContext = ws.app.state.ctx
    await ws.accept()
    events = ctx.queue.subscribe()

    async def drain_client() -> None:
        try:
            while True:  # consume pings/closes; returns when the client goes away
                await ws.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            return

    reader = asyncio.create_task(drain_client())
    try:
        while True:
            getter = asyncio.create_task(events.get())
            done, _ = await asyncio.wait({getter, reader}, return_when=asyncio.FIRST_COMPLETED)
            if reader in done:
                getter.cancel()
                return
            await ws.send_json(getter.result())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        reader.cancel()
        ctx.queue.unsubscribe(events)
