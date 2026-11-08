"""The built Vue app, served by FastAPI (no separate web server)."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# Vite puts a content hash in every asset file name, so they never change.
IMMUTABLE = "public, max-age=31536000, immutable"
# index.html must be revalidated so a new build is picked up on reload.
REVALIDATE = "no-cache"


class FrontendFiles(StaticFiles):
    def __init__(self, directory: str):
        super().__init__(directory=directory, html=True)

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as e:
            # Routes are hash-based (#/library), but paths like /settings were
            # served index.html by nginx; keep them working. API, WebSocket and
            # file-looking paths still 404.
            if e.status_code != 404 or path.startswith(("api/", "ws/")) or "." in path.rsplit("/", 1)[-1]:
                raise
            response = await super().get_response("index.html", scope)
            path = "index.html"
        response.headers["Cache-Control"] = IMMUTABLE if path.startswith("assets/") else REVALIDATE
        return response
