from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..services import downloads as service

router = APIRouter()


class DownloadOptions(BaseModel):
    format: str = ""  # m4b/mp3; "" = the default from Settings
    split_chapters: bool = False
    include_pdf: bool = True  # save the companion PDF next to the audiobook, if there is one
    kind: str = "audio"  # audio, or pdf for only the companion PDF

    def options(self) -> service.DownloadOptions:
        return service.DownloadOptions(self.format, self.split_chapters, self.include_pdf, self.kind)


class EnqueueRequest(DownloadOptions):
    book_id: int
    audible_id: str = ""  # accepted for older clients; the book's own ASIN is used
    account_id: int | None = None


class BulkEnqueueRequest(DownloadOptions):
    book_ids: list[int]


@router.post("/downloads", status_code=202)
async def enqueue_download(req: EnqueueRequest, ctx: AppContext = Depends(get_ctx)):
    try:
        job_id = await service.enqueue(ctx.db, ctx.queue, ctx.config, req.book_id, req.options(), req.account_id)
    except service.InvalidOptions as e:
        raise HTTPException(400, str(e))
    if job_id is None:
        raise HTTPException(404, "book not found for this account")
    return {"job_id": job_id}


@router.post("/downloads/bulk", status_code=202)
async def enqueue_downloads(req: BulkEnqueueRequest, ctx: AppContext = Depends(get_ctx)):
    """Queue several books at once (in the order given). Unknown ids are skipped."""
    try:
        jobs = await service.enqueue_many(ctx.db, ctx.queue, ctx.config, req.book_ids, req.options())
    except service.InvalidOptions as e:
        raise HTTPException(400, str(e))
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
