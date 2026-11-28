from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, Query, Response

from ..config import NamingPreset
from ..deps import DownloadSvc, LayoutMoveSvc, LibrarySvc
from ..services.downloads import NoPdf, PdfFailed
from ..services.book_files import BookFiles
from ..services.layout_move import MoveInProgress
from ..services.library import EXPORT_FIELDS, MAX_PAGE_SIZE, PAGE_SIZE, InvalidSort
from .schemas import BookPatch, BulkUpdate, MoveRequest

router = APIRouter()


@router.get("/library")
def list_library(
    library_svc: LibrarySvc,
    q: str = "",
    page: int = 1,
    limit: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    sort: str | None = None,
    order: str | None = None,
    account_id: int | None = None,
):
    try:
        return library_svc.list_books(search=q, sort=sort, order=order, page=page, limit=limit,
                                      account_id=account_id)
    except InvalidSort:
        raise HTTPException(400, "invalid sort or order")


@router.post("/library/bulk", status_code=204)
def bulk_update(req: BulkUpdate, library_svc: LibrarySvc):
    library_svc.set_hidden(req.book_ids, req.is_hidden)
    return Response(status_code=204)


@router.get("/library/move-preview")
def preview_move(layout_move_svc: LayoutMoveSvc, naming: NamingPreset):
    """What moving the downloaded books to this layout would do. Nothing is moved."""
    return layout_move_svc.preview(naming)


@router.post("/library/move")
def move_books(req: MoveRequest, layout_move_svc: LayoutMoveSvc):
    """Move the downloaded books that can safely move to this layout."""
    try:
        return layout_move_svc.move(req.naming)
    except MoveInProgress as e:
        raise HTTPException(409, str(e))


@router.get("/library/export")
def export_library(library_svc: LibrarySvc, format: str = Query("json")):
    if format not in ("json", "csv"):
        raise HTTPException(400, "format must be 'json' or 'csv'")
    rows = library_svc.export_rows()
    if format == "json":
        return Response(
            json.dumps(rows, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=library.json"},
        )
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(EXPORT_FIELDS)
    for r in rows:
        w.writerow([
            r["audible_id"], r["title"], r["authors"], r["narrators"], r["series"],
            r["length_minutes"], r["publisher"], r["language"], f'{r["audible_rating"]:.2f}',
            r["download_status"], str(r["is_finished"]).lower(), r["tags"], r["date_added"],
        ])
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=library.csv"},
    )


@router.post("/library/rescan")
def rescan_files(library_svc: LibrarySvc):
    try:
        return library_svc.rescan()._asdict()
    except OSError as e:
        raise HTTPException(500, f"cannot read output directory: {e}")


@router.get("/library/{book_id}")
def get_book(book_id: int, library_svc: LibrarySvc):
    book = library_svc.get_book(book_id)
    if book is None:
        raise HTTPException(404, "book not found")
    book["planned_path"] = library_svc.planned_path(book_id)
    return book


@router.get("/library/{book_id}/files", response_model=BookFiles)
def get_book_files(book_id: int, library_svc: LibrarySvc):
    """The files this book has on disk."""
    files = library_svc.book_files(book_id)
    if files is None:
        raise HTTPException(404, "book not found")
    return files


@router.post("/library/{book_id}/pdf")
async def save_pdf(book_id: int, download_svc: DownloadSvc, account_id: int | None = None):
    """Save the book's companion PDF now, without a download (nothing on the Downloads page)."""
    try:
        path = await download_svc.save_pdf(book_id, account_id)
    except NoPdf:
        raise HTTPException(404, "this title has no companion PDF")
    except PdfFailed as e:
        raise HTTPException(502, str(e))
    except OSError as e:
        raise HTTPException(500, f"saving PDF: {e}")
    if path is None:
        raise HTTPException(404, "book not found for this account")
    return {"file_path": path}


@router.patch("/library/{book_id}", status_code=204)
def update_book(book_id: int, patch: BookPatch, library_svc: LibrarySvc):
    library_svc.update_book(book_id, tags=patch.tags, is_finished=patch.is_finished, is_hidden=patch.is_hidden)
    return Response(status_code=204)
