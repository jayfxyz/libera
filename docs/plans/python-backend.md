# Plan: one Python service instead of Go backend + Python sidecar + nginx

## Why

Today a running install is three containers:

- **frontend**: nginx serving the Vue build and proxying `/api` and `/ws`
- **backend**: Go API, SQLite, download queue, ffmpeg
- **audible-svc**: FastAPI sidecar wrapping the `audible` / `audible-cli` Python libraries

Every Audible call crosses an HTTP hop from Go to the sidecar, tracing is split
across two services, and users run three containers. The sidecar exists only
because the Audible client libraries are Python. Moving the backend to Python
removes the hop, and FastAPI serving the built frontend removes nginx: **one
image, one container**.

## Target

```
server/
  app/
    main.py          FastAPI app: lifespan, routers, /ws, /health, static frontend
    config.py        env defaults + settings stored in the DB
    db.py            SQLite (stdlib sqlite3), schema, migrations
    schema.sql       unchanged from the Go backend
    telemetry.py     optional OTLP tracing (OTEL_EXPORTER_OTLP_ENDPOINT)
    audible_api/     in-process Audible client (was the sidecar)
      storage.py     token files in ACCOUNTS_DIR
      auth.py        maplanding login: start + complete
      library.py     fetch + normalise the library
      content.py     download info (AAXC, AAX fallback, license denial), chapters, PDF
    library.py       import, sort, search, rescan, export queries
    jobs/
      queue.py       asyncio queue, workers, progress broadcast, cancel
      download.py    one download job end to end
      ffmpeg.py      decrypt command
      outline.py     chapter flattening, ffmetadata, .cue, .chapters.json
      chapters.py    split into per-chapter files
      filename.py    filename/folder templates
    api/             routers: accounts, library, downloads, settings, ws
    static.py        SPA files with cache headers
  tests/             pytest, ported from the Go and sidecar tests
Dockerfile           node build stage → python:3.12-slim-trixie + ffmpeg
```

## Decisions

- **API stays identical.** Same paths, methods, status codes and JSON fields, so
  the frontend doesn't change. `/ws/downloads` stays at the root (and under `/api`).
- **Schema and data stay identical.** `schema.sql` is copied as is; existing
  databases open without migration. The image pins `python:3.12-slim-trixie`
  because the search index needs SQLite ≥ 3.43 (`contentless_delete`).
- **Paths keep today's layout** inside `/data`: DB at `/data/db/libation.db`,
  Audible tokens at `/data/accounts`. Existing `./data` mounts keep working;
  only the tokens move, out of the old `audible-tokens` volume.
- **No blocking on the event loop.** SQLite calls go through a single
  lock-guarded connection used from worker threads (sync route handlers run in
  FastAPI's threadpool; the async job worker uses `asyncio.to_thread`). ffmpeg
  runs via `asyncio.create_subprocess_exec`; downloads stream with async `httpx`.
- **One uvicorn worker.** The job queue and WebSocket subscribers live in
  memory, as they did in Go.
- **Static frontend**: `index.html` with `Cache-Control: no-cache` (so a new
  build is picked up on reload), hashed `/assets/*` as `immutable`, gzip.
  Hash routing (`#/...`) means no SPA fallback route is needed.
- **Tracing**: one OpenTelemetry setup; FastAPI and httpx instrumented; job
  spans (`job.process`, `job.download`, `job.chapters`, `job.ffmpeg`) are
  children of the request that enqueued them.

Small behaviour changes, each deliberate:

- Cancelling a **queued** download works (Go only cancelled running ones).
- Search matches word prefixes (`atom` finds *Atomic Habits*) and no longer
  fails on punctuation; Go passed the raw text to FTS `MATCH`.

## Steps

1. **Skeleton**: package layout, config, DB + schema, settings API, health,
   telemetry, Dockerfile, test setup.
2. **Port features**: accounts + login, library (list/sort/search/detail/
   update/rescan/export/scan), downloads (queue, job, ffmpeg, chapters, PDF,
   cancel, WebSocket). Port every Go and sidecar test.
3. **Serve the frontend** from FastAPI; Vite dev proxy points at uvicorn.
4. **Switch compose to one container**; migrate the Pi install (move tokens);
   end-to-end check: login state, scan, sort, download with chapters.
5. **Delete** `backend/`, `audible-svc/`, `nginx.conf`, the old Dockerfiles;
   update docs.

## Upgrading an existing install

The database stays where it is (`./data/db/libation.db`). Only the Audible
login tokens move, out of the old sidecar's Docker volume:

```sh
docker run --rm -v libation-web_audible-tokens:/from:ro -v "$PWD/data":/to alpine \
  sh -c 'mkdir -p /to/accounts && cp -a /from/accounts/. /to/accounts/ && chmod 600 /to/accounts/*'
# if PUID/PGID are set in .env, give that user the folder: chown -R <PUID>:<PGID> data/accounts
docker compose up -d --build --remove-orphans   # replaces the three old containers
```

Once it works, the old volume can go: `docker volume rm libation-web_audible-tokens`.
