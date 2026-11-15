"""Shared application state, reachable from route handlers via ``get_ctx``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request

from .config import Config
from .db import Database

if TYPE_CHECKING:
    from .audible_api.client import AudibleClient
    from .services.downloads import DownloadEvents, DownloadsService
    from .services.task_queue import TaskQueueService
    from .services.task_worker import TaskWorkerService


@dataclass
class AppContext:
    config: Config
    db: Database
    audible: "AudibleClient"
    downloads: "DownloadsService"
    download_events: "DownloadEvents"
    task_queue: "TaskQueueService"
    task_worker: "TaskWorkerService"


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
