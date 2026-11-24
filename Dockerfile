# One image: the Vue frontend, built here, served by the FastAPI backend.
#   docker build -t libera .                                  # the app
#   docker build --target test -t libera-test . && docker run --rm libera-test   # the tests

FROM ghcr.io/astral-sh/uv:0.7 AS uv

FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build-only

# trixie: SQLite >= 3.43 is required by the search index (contentless_delete).
FROM python:3.12-slim-trixie AS python-base
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python-base AS test
RUN uv sync --frozen --no-install-project
COPY server/ .
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM python-base
COPY server/app ./app
COPY --from=frontend /frontend/dist ./frontend

ENV DATABASE_PATH=/data/db/libera.db \
    ACCOUNTS_DIR=/data/accounts \
    OUTPUT_DIR=/audiobooks \
    FRONTEND_DIR=/app/frontend \
    PYTHONUNBUFFERED=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Exactly one worker: task workers and event-stream subscribers live in memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
