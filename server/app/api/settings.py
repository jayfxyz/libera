from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..services import settings as service

router = APIRouter()


@router.get("/settings")
def get_settings(ctx: AppContext = Depends(get_ctx)):
    return service.current(ctx.config)


class SettingsPatch(BaseModel):
    # Unknown fields (the UI sends the whole settings object back) are ignored.
    output_dir: str | None = None
    download_workers: int | None = None
    default_format: str | None = None
    filename_template: str | None = None
    folder_template: str | None = None


@router.patch("/settings", status_code=204)
def update_settings(patch: SettingsPatch, ctx: AppContext = Depends(get_ctx)):
    try:
        service.update(ctx.db, ctx.config, patch.model_dump())
    except service.InvalidSetting as e:
        raise HTTPException(400, str(e))
    return Response(status_code=204)
