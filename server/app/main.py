"""FastAPI application: API, download-progress WebSocket and the built frontend."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse

from .api import accounts as accounts_api
from .api import downloads as downloads_api
from .api import library as library_api
from .api import settings as settings_api
from .audible_api.client import AudibleClient
from .config import Config
from .context import AppContext
from .db import Database
from .jobs.download import make_runner
from .jobs.queue import DownloadQueue
from .services import settings as settings_service
from .services.task_queue import TaskQueueService
from .services.task_worker import TaskWorkerService
from .static import FrontendFiles
from .tasks.signals import TaskSignals
from .telemetry import init_tracing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app(config: Config | None = None, db: Database | None = None,
               audible: AudibleClient | None = None, runner=None) -> FastAPI:
    """Build the app. Tests pass their own db, Audible client and job runner."""
    config = config or Config.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = db or Database(config.database_path)
        database.migrate()
        settings_service.load_saved(database, config)
        client = audible or AudibleClient(config.accounts_dir)
        queue = DownloadQueue(runner or make_runner(database, client), database, workers=config.download_workers)
        queue.start()
        signals = TaskSignals()
        task_queue = TaskQueueService(database, signals)
        task_worker = TaskWorkerService(database, signals, workers=config.download_workers)
        task_worker.start()  # no handlers yet: downloads still run on DownloadQueue until phase 2
        app.state.ctx = AppContext(config=config, db=database, audible=client, queue=queue,
                                   task_queue=task_queue, task_worker=task_worker)
        log.info("ready: db=%s output=%s workers=%d", config.database_path, config.output_dir,
                 config.download_workers)
        try:
            yield
        finally:
            await task_worker.stop()
            await queue.stop()
            if db is None:
                database.close()

    app = FastAPI(title="libation-web", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/health", response_class=PlainTextResponse)
    def health():
        return "ok"

    for module in (accounts_api, library_api, downloads_api, settings_api):
        app.include_router(module.router, prefix="/api")
    for path in ("/ws/downloads", "/api/ws/downloads"):
        app.add_api_websocket_route(path, downloads_api.download_progress)

    # The built frontend, last so the API and WebSocket routes match first.
    if config.frontend_dir and os.path.isdir(config.frontend_dir):
        app.mount("/", FrontendFiles(config.frontend_dir), name="frontend")
    elif config.frontend_dir:
        log.warning("FRONTEND_DIR %s not found; serving the API only", config.frontend_dir)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    init_tracing(app)
    return app


app = create_app()
