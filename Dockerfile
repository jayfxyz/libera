# One image: the Vue frontend, built here, served by the FastAPI backend.
#   docker build -t libation-web .                                  # the app
#   docker build --target test -t libation-web-test . && docker run --rm libation-web-test   # the tests

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# trixie: SQLite >= 3.43 is required by the search index (contentless_delete).
FROM python:3.12-slim-trixie AS python-base
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python-base AS test
COPY server/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY server/ .
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM python-base
COPY server/app ./app
COPY --from=frontend /frontend/dist ./frontend

ENV DATABASE_PATH=/data/db/libation.db \
    ACCOUNTS_DIR=/data/accounts \
    OUTPUT_DIR=/audiobooks \
    FRONTEND_DIR=/app/frontend \
    PYTHONUNBUFFERED=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Exactly one worker: the download queue and WebSocket subscribers live in memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
