from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..config import FORMATS
from ..context import AppContext, get_ctx

router = APIRouter()


@router.get("/settings")
def get_settings(ctx: AppContext = Depends(get_ctx)):
    c = ctx.config
    return {
        "app_url": c.app_url,
        "output_dir": c.output_dir,
        "download_workers": c.download_workers,
        "default_format": c.default_format,
        "filename_template": c.filename_template,
        "folder_template": c.folder_template,
    }


class SettingsPatch(BaseModel):
    # Unknown fields (the UI sends the whole settings object back) are ignored.
    output_dir: str | None = None
    download_workers: int | None = None
    default_format: str | None = None
    filename_template: str | None = None
    folder_template: str | None = None


@router.patch("/settings", status_code=204)
def update_settings(patch: SettingsPatch, ctx: AppContext = Depends(get_ctx)):
    if patch.default_format is not None and patch.default_format not in FORMATS:
        raise HTTPException(400, "default_format must be 'm4b' or 'mp3'")
    for key, value in patch.model_dump(exclude_none=True).items():
        stored = str(value)
        ctx.db.set_setting(key, stored)
        ctx.config.apply(key, stored)
    return Response(status_code=204)
