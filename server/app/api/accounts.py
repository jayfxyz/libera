from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..audible_api.auth import LoginError
from ..audible_api.storage import AccountNotFound
from ..context import AppContext, get_ctx
from ..services import accounts as service

router = APIRouter()


@router.get("/accounts")
def list_accounts(ctx: AppContext = Depends(get_ctx)):
    return service.list_accounts(ctx.db)


class AccountPatch(BaseModel):
    account_name: str | None = None


@router.patch("/accounts/{account_id}", status_code=204)
def update_account(account_id: int, patch: AccountPatch, ctx: AppContext = Depends(get_ctx)):
    if patch.account_name is not None:
        service.rename(ctx.db, account_id, patch.account_name)
    return Response(status_code=204)


@router.post("/accounts")
def create_account():
    raise HTTPException(405, "use POST /api/accounts/auth/start")


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, ctx: AppContext = Depends(get_ctx)):
    service.remove(ctx.db, account_id)
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
        email = service.complete_login(ctx.db, ctx.audible, req.state, req.response_url)
    except LoginError as e:
        raise HTTPException(e.status, str(e))
    return {"email": email}


@router.post("/accounts/{account_id}/scan")
async def scan_library(account_id: int, ctx: AppContext = Depends(get_ctx)):
    try:
        imported = await service.scan(ctx.db, ctx.audible, account_id)
    except AccountNotFound as e:
        raise HTTPException(404, str(e))
    except service.ScanFailed as e:
        raise HTTPException(502, str(e))
    if imported is None:
        raise HTTPException(404, "account not found")
    return {"imported": imported}
