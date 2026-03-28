import logging
logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from routes.auth import router as auth_router
from routes.library import router as library_router
from routes.download import router as download_router

app = FastAPI(title="audible-svc", docs_url=None, redoc_url=None)

app.include_router(auth_router, prefix="/auth")
app.include_router(library_router, prefix="/library")
app.include_router(download_router, prefix="/download")


@app.get("/health")
def health():
    return {"status": "ok"}
