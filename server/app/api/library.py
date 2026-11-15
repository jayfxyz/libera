from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..deps import DownloadSvc
from ..services import library
from ..services.downloads import NoPdf, PdfFailed

router = APIRouter()


@router.get("/library")
def list_library(
    q: str = "",
    page: int = 1,
    limit: int = Query(library.PAGE_SIZE, ge=1, le=library.MAX_PAGE_SIZE),
    sort: str | None = None,
    order: str | None = None,
    account_id: int | None = None,
    ctx: AppContext = Depends(get_ctx),
):
    try:
        return library.list_books(ctx.db, search=q, sort=sort, order=order, page=page, limit=limit,
                                  account_id=account_id)
    except library.InvalidSort:
        raise HTTPException(400, "invalid sort or order")


class BulkUpdate(BaseModel):
    book_ids: list[int]
    is_hidden: bool


@router.post("/library/bulk", status_code=204)
def bulk_update(req: BulkUpdate, ctx: AppContext = Depends(get_ctx)):
    library.set_hidden(ctx.db, req.book_ids, req.is_hidden)
    return Response(status_code=204)


@router.get("/library/export")
def export_library(format: str = Query("json"), ctx: AppContext = Depends(get_ctx)):
    if format not in ("json", "csv"):
        raise HTTPException(400, "format must be 'json' or 'csv'")
    rows = library.export_rows(ctx.db)
    if format == "json":
        return Response(
            json.dumps(rows, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=library.json"},
        )
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(library.EXPORT_FIELDS)
    for r in rows:
        w.writerow([
            r["audible_id"], r["title"], r["authors"], r["narrators"], r["series"],
            r["length_minutes"], r["publisher"], r["language"], f'{r["audible_rating"]:.2f}',
            r["liberation_status"], str(r["is_finished"]).lower(), r["tags"],
            "" if r["user_rating"] is None else r["user_rating"], r["date_added"],
        ])
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=library.csv"},
    )


@router.post("/library/rescan")
def rescan_files(ctx: AppContext = Depends(get_ctx)):
    try:
        return {"matched": library.rescan(ctx.db, ctx.config.output_dir)}
    except OSError as e:
        raise HTTPException(500, f"cannot read output directory: {e}")


@router.get("/library/{book_id}")
def get_book(book_id: int, ctx: AppContext = Depends(get_ctx)):
    book = library.get_book(ctx.db, book_id)
    if book is None:
        raise HTTPException(404, "book not found")
    book["planned_path"] = library.planned_path(ctx.db, book_id, ctx.config)
    return book


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


class BookPatch(BaseModel):
    tags: str | None = None
    user_rating: float | None = None
    is_finished: bool | None = None
    is_hidden: bool | None = None


@router.patch("/library/{book_id}", status_code=204)
def update_book(book_id: int, patch: BookPatch, ctx: AppContext = Depends(get_ctx)):
    library.update_book(ctx.db, book_id, tags=patch.tags, user_rating=patch.user_rating,
                        is_finished=patch.is_finished, is_hidden=patch.is_hidden)
    return Response(status_code=204)
