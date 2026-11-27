"""Shared application state, kept on ``app.state.ctx``. Routes reach the
services through the typed dependencies in deps.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .config import Config
from .db import Database
from .events import EventBus

if TYPE_CHECKING:
    from .audible_api.client import AudibleClient
    from .services.accounts import AccountsService
    from .services.downloads import DownloadsService
    from .services.layout_move import LibraryMoveService
    from .services.library import LibraryService
    from .services.settings import SettingsService
    from .services.task_queue import TaskQueueService
    from .services.task_worker import TaskWorker
    from .tasks.registry import TaskRegistry


@dataclass
class AppContext:
    config: Config
    db: Database
    audible: "AudibleClient"
    accounts: "AccountsService"
    library: "LibraryService"
    layout_move: "LibraryMoveService"
    settings: "SettingsService"
    downloads: "DownloadsService"
    events: EventBus
    task_queue: "TaskQueueService"
    task_registry: "TaskRegistry"
    task_workers: "list[TaskWorker]"
