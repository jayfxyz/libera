from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..deps import SettingsSvc
from ..services.settings import InvalidSetting
from .schemas import SettingsPatch

router = APIRouter()


@router.get("/settings")
def get_settings(settings_svc: SettingsSvc):
    return settings_svc.current()


@router.patch("/settings", status_code=204)
def update_settings(patch: SettingsPatch, settings_svc: SettingsSvc):
    try:
        settings_svc.update(patch.model_dump())
    except InvalidSetting as e:
        raise HTTPException(400, str(e))
    return Response(status_code=204)
