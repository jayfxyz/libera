"""FastAPI application: API, download-progress WebSocket and the built frontend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from .api import settings as settings_api
from .config import Config
from .context import AppContext
from .db import Database
from .telemetry import init_tracing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def create_app(config: Config | None = None, db: Database | None = None) -> FastAPI:
    config = config or Config.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = db or Database(config.database_path)
        database.migrate()
        config.apply_overrides(database.all_settings())
        app.state.ctx = AppContext(config=config, db=database, audible=None, queue=None)  # type: ignore[arg-type]
        try:
            yield
        finally:
            if db is None:
                database.close()

    app = FastAPI(title="libation-web", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/health", response_class=PlainTextResponse)
    def health():
        return "ok"

    app.include_router(settings_api.router, prefix="/api")

    init_tracing(app)
    return app


app = create_app()
