"""Typed FastAPI dependencies: one per service, so routes declare exactly what they use.

    def list_downloads(download_svc: DownloadSvc): ...
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .config import Config
from .services.downloads import DownloadsService


def get_download_svc(request: Request) -> DownloadsService:
    return request.app.state.ctx.downloads


def get_config(request: Request) -> Config:
    return request.app.state.ctx.config


DownloadSvc = Annotated[DownloadsService, Depends(get_download_svc)]
ConfigDep = Annotated[Config, Depends(get_config)]
