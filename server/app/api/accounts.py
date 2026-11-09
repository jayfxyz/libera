from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import library
from ..audible_api.auth import LoginError
from ..audible_api.storage import AccountNotFound
from ..context import AppContext, get_ctx
from ..db import iso_utc

router = APIRouter()


@router.get("/accounts")
def list_accounts(ctx: AppContext = Depends(get_ctx)):
    rows = ctx.db.query(
        "SELECT id, account_name, email, locale, library_scan_enabled, last_scanned_at FROM accounts ORDER BY id"
    )
    return [
        {**dict(r), "library_scan_enabled": bool(r["library_scan_enabled"]),
         "last_scanned_at": iso_utc(r["last_scanned_at"])}
        for r in rows
    ]


class AccountPatch(BaseModel):
    account_name: str | None = None


@router.patch("/accounts/{account_id}", status_code=204)
def update_account(account_id: int, patch: AccountPatch, ctx: AppContext = Depends(get_ctx)):
    if patch.account_name is not None:
        ctx.db.execute("UPDATE accounts SET account_name = ? WHERE id = ?", (patch.account_name, account_id))
    return Response(status_code=204)


@router.post("/accounts")
def create_account():
    raise HTTPException(405, "use POST /api/accounts/auth/start")


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.transaction() as conn:
        conn.execute("DELETE FROM library_books WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    return Response(status_code=204)


class AuthStart(BaseModel):
    locale: str = ""
    name: str = ""


@router.post("/accounts/auth/start")
def auth_start(req: AuthStart, ctx: AppContext = Depends(get_ctx)):
    try:
        url, state = ctx.audible.start_login(req.locale or "us", req.name)
    except LoginError as e:
        raise HTTPException(e.status, str(e))
    return {"auth_url": url, "state": state}


class AuthComplete(BaseModel):
    state: str = ""
    response_url: str = ""


@router.post("/accounts/auth/complete")
def auth_complete(req: AuthComplete, ctx: AppContext = Depends(get_ctx)):
    """Called after the user logged in at Amazon and pasted the maplanding URL."""
    if not req.state or not req.response_url:
        raise HTTPException(400, "state and response_url are required")
    try:
        result = ctx.audible.complete_login(req.state, req.response_url)
    except LoginError as e:
        raise HTTPException(e.status, str(e))
    ctx.db.execute(
        """INSERT INTO accounts (account_name, email, locale, audible_account_id) VALUES (?, ?, ?, ?)
           ON CONFLICT(email) DO UPDATE SET
               account_name = excluded.account_name,
               locale = excluded.locale,  -- the saved login is for this region now
               audible_account_id = excluded.audible_account_id""",
        (result.name, result.email, result.locale, result.account_id),
    )
    return {"email": result.email}


@router.post("/accounts/{account_id}/scan")
async def scan_library(account_id: int, ctx: AppContext = Depends(get_ctx)):
    audible_account_id = await run_in_threadpool(
        ctx.db.scalar, "SELECT audible_account_id FROM accounts WHERE id = ?", (account_id,)
    )
    if audible_account_id is None:
        raise HTTPException(404, "account not found")
    try:
        books = await ctx.audible.get_library(audible_account_id)
    except AccountNotFound as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"Audible library fetch failed: {e}")
    imported = await run_in_threadpool(library.import_library, ctx.db, account_id, books)
    await run_in_threadpool(
        ctx.db.execute, "UPDATE accounts SET last_scanned_at = CURRENT_TIMESTAMP WHERE id = ?", (account_id,)
    )
    return {"imported": imported}
