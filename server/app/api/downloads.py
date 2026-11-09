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


KINDS = ("audio", "pdf")  # audio: the audiobook (+ companion PDF); pdf: only the companion PDF


class DownloadOptions(BaseModel):
    format: str = ""  # m4b/mp3; "" = the default from Settings
    split_chapters: bool = False
    include_pdf: bool = True  # save the companion PDF next to the audiobook, if there is one
    kind: str = "audio"


class EnqueueRequest(DownloadOptions):
    book_id: int
    audible_id: str = ""  # accepted for older clients; the book's own ASIN is used
    account_id: int | None = None


class BulkEnqueueRequest(DownloadOptions):
    book_ids: list[int]


def _validate(opts: DownloadOptions, ctx: AppContext) -> str:
    fmt = opts.format or ctx.config.default_format
    if fmt not in FORMATS:
        raise HTTPException(400, "format must be 'm4b' or 'mp3'")
    if opts.kind not in KINDS:
        raise HTTPException(400, "kind must be 'audio' or 'pdf'")
    return fmt


def _make_job(meta: dict, fmt: str, opts: DownloadOptions, ctx: AppContext) -> DownloadJob:
    settings = ctx.config.snapshot()
    book_id = meta["book_id"]
    return DownloadJob(
        id=f"dl-{book_id}-{time.time_ns() // 1000}",
        book_id=book_id,
        audible_id=meta["audible_id"],
        account_id=meta["account_id"],
        audible_account_id=meta["audible_account_id"],
        format=fmt,
        output_dir=settings.output_dir,
        filename_template=settings.filename_template,
        folder_template=settings.folder_template,
        split_chapters=opts.split_chapters,
        include_pdf=opts.include_pdf,
        kind=opts.kind,
        **library.naming_data(meta),
    )


def _enqueue(job: DownloadJob, ctx: AppContext) -> None:
    with tracer.start_as_current_span("job.enqueue", attributes={
        "job.id": job.id, "job.asin": job.audible_id, "job.format": job.format, "job.kind": job.kind,
    }):
        ctx.queue.enqueue(job)


def _meta(db: Database, book_id: int, account_id: int | None) -> dict | None:
    meta = library.book_meta(db, book_id, account_id)
    return None if meta is None else {**meta, "book_id": book_id}


@router.post("/downloads", status_code=202)
async def enqueue_download(req: EnqueueRequest, ctx: AppContext = Depends(get_ctx)):
    fmt = _validate(req, ctx)
    meta = await run_in_threadpool(_meta, ctx.db, req.book_id, req.account_id)
    if meta is None:
        raise HTTPException(404, "book not found for this account")
    job = _make_job(meta, fmt, req, ctx)
    _enqueue(job, ctx)
    return {"job_id": job.id}


@router.post("/downloads/bulk", status_code=202)
async def enqueue_downloads(req: BulkEnqueueRequest, ctx: AppContext = Depends(get_ctx)):
    """Queue several books at once (in the order given). Unknown ids are skipped."""
    fmt = _validate(req, ctx)
    jobs = []
    for book_id in dict.fromkeys(req.book_ids):  # de-duplicated, order kept
        meta = await run_in_threadpool(_meta, ctx.db, book_id, None)
        if meta is not None:
            job = _make_job(meta, fmt, req, ctx)
            _enqueue(job, ctx)
            jobs.append({"job_id": job.id, "book_id": book_id})
    return {"jobs": jobs}


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
