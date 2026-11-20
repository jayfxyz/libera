"""Typed FastAPI dependencies: one per service, so routes declare exactly what they use.

    def list_downloads(download_svc: DownloadSvc): ...
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .events import EventBus
from .services.accounts import AccountsService
from .services.downloads import DownloadsService
from .services.library import LibraryService
from .services.settings import SettingsService


def get_account_svc(request: Request) -> AccountsService:
    return request.app.state.ctx.accounts


def get_download_svc(request: Request) -> DownloadsService:
    return request.app.state.ctx.downloads


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.ctx.events


def get_library_svc(request: Request) -> LibraryService:
    return request.app.state.ctx.library


def get_settings_svc(request: Request) -> SettingsService:
    return request.app.state.ctx.settings


AccountSvc = Annotated[AccountsService, Depends(get_account_svc)]
DownloadSvc = Annotated[DownloadsService, Depends(get_download_svc)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
LibrarySvc = Annotated[LibraryService, Depends(get_library_svc)]
SettingsSvc = Annotated[SettingsService, Depends(get_settings_svc)]
