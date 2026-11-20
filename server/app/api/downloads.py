from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..deps import DownloadSvc
from ..services.downloads import InvalidOptions
from .schemas import BulkEnqueueRequest, EnqueueRequest

router = APIRouter()


@router.post("/downloads", status_code=202)
def enqueue_download(req: EnqueueRequest, download_svc: DownloadSvc):
    try:
        download_id = download_svc.enqueue(req.book_id, format=req.format, split_chapters=req.split_chapters,
                                           account_id=req.account_id)
    except InvalidOptions as e:
        raise HTTPException(400, str(e))
    if download_id is None:
        raise HTTPException(404, "book not found for this account")
    return {"id": download_id}


@router.post("/downloads/bulk", status_code=202)
def enqueue_downloads(req: BulkEnqueueRequest, download_svc: DownloadSvc):
    """Queue several books at once (in the order given). Unknown ids are skipped."""
    try:
        return {"downloads": download_svc.enqueue_many(req.book_ids, format=req.format,
                                                  split_chapters=req.split_chapters)}
    except InvalidOptions as e:
        raise HTTPException(400, str(e))


@router.get("/downloads")
def list_downloads(download_svc: DownloadSvc):
    """Queued and running downloads, plus recent history (survives restarts)."""
    return download_svc.list()


@router.delete("/downloads/{download_id}", status_code=204)
def cancel_download(download_id: str, download_svc: DownloadSvc):
    if not download_svc.cancel(download_id):
        raise HTTPException(404, "no running or queued download with that id")
    return Response(status_code=204)


@router.post("/downloads/{download_id}/retry", status_code=202)
def retry_download(download_id: str, download_svc: DownloadSvc):
    """Run a failed download again: only the decrypt step if its downloaded file is still kept."""
    if not download_svc.retry(download_id):
        raise HTTPException(404, "no failed download with that id")
    return {"id": download_id}

