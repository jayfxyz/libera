"""FastAPI application: API, event stream and the built frontend."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse

from .api import accounts as accounts_api
from .api import downloads as downloads_api
from .api import events as events_api
from .api import library as library_api
from .api import settings as settings_api
from .audible_api.client import AudibleClient
from .config import Config
from .context import AppContext
from .db import Database
from .events import EventBus
from .services.accounts import AccountsService
from .services.downloads import DownloadsService
from .services.layout_move import LibraryMoveService
from .services.library import LibraryService
from .services.settings import SettingsService
from .services.task_queue import TaskQueueService
from .services.task_worker import TaskWorker
from .static import FrontendFiles
from .tasks.downloads import DecryptBook, DownloadBook, DownloadHandlers, Pipeline
from .tasks.registry import TaskRegistry
from .tasks.signals import TaskSignals
from .telemetry import init_tracing

_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
if not isinstance(_log_level, int):
    _log_level = logging.INFO
logging.basicConfig(level=_log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app(config: Config | None = None, db: Database | None = None,
               audible: AudibleClient | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    """Build the app. Tests pass their own db, Audible client and download pipeline."""
    config = config or Config.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = db or Database(config.database_path)
        database.migrate()
        settings = SettingsService(database, config)
        settings.load_saved()
        client = audible or AudibleClient(config.accounts_dir)
        events = EventBus()
        events.attach(asyncio.get_running_loop())
        library = LibraryService(database, config, events)
        layout_move = LibraryMoveService(database, config, library)
        accounts = AccountsService(database, client, library)

        # Queue & workers
        signals = TaskSignals()
        task_queue = TaskQueueService(database, signals)
        downloads = DownloadsService(database, config, task_queue, events, client, library)
        handlers = DownloadHandlers(downloads, pipeline or Pipeline(client))
        task_registry = TaskRegistry()
        task_registry.add(DownloadBook, handlers.download_book)
        task_registry.add(DecryptBook, handlers.decrypt_book)
        task_workers = [
            TaskWorker(queue=task_queue, registry=task_registry, signals=signals,
                       task_type=DownloadBook.name, concurrency=config.download_workers),
            TaskWorker(queue=task_queue, registry=task_registry, signals=signals,
                       task_type=DecryptBook.name, concurrency=1),
        ]
        task_queue.recover(known_types=task_registry.types)  # tasks the last shutdown interrupted, or no one can run
        for worker in task_workers:
            worker.start()
        downloads.start()  # then fails downloads left with no live task

        app.state.ctx = AppContext(config=config, db=database, audible=client, accounts=accounts, library=library,
                                   layout_move=layout_move,
                                   settings=settings, downloads=downloads, events=events, task_queue=task_queue,
                                   task_registry=task_registry, task_workers=task_workers)
        log.info("ready: db=%s output=%s workers=%d", config.database_path, config.output_dir,
                 config.download_workers)
        try:
            yield
        finally:
            await asyncio.gather(*(worker.stop() for worker in task_workers))
            if db is None:
                database.close()

    app = FastAPI(title="libera", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/health", response_class=PlainTextResponse)
    def health():
        return "ok"

    for module in (accounts_api, library_api, downloads_api, events_api, settings_api):
        app.include_router(module.router, prefix="/api")

    # The built frontend, last so the API routes match first.
    if config.frontend_dir and os.path.isdir(config.frontend_dir):
        # Only the built frontend is compressed: gzip would hold back the event stream.
        app.mount("/", GZipMiddleware(FrontendFiles(config.frontend_dir), minimum_size=1024), name="frontend")
    elif config.frontend_dir:
        log.warning("FRONTEND_DIR %s not found; serving the API only", config.frontend_dir)

    init_tracing(app)
    return app


app = create_app()
