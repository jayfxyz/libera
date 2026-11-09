# Plan: repositories, services, Alembic and a persistent download queue

## Where we are

- **API layer**: FastAPI routers in `app/api/`. Some contain SQL
  (`api/accounts.py`) or business logic (building download jobs).
- **No service layer**: logic sits in `app/library.py` (import, sort,
  rescan, export, naming), `app/jobs/download.py` and the routes.
- **No repository layer**: raw `sqlite3` behind a lock (`app/db.py`); ~55
  SQL statements across `app/library.py`, `app/db.py` and routes.
- **Migrations**: `schema.sql` (`CREATE … IF NOT EXISTS`) plus a list of
  `ALTER TABLE … ADD COLUMN` that ignore "already exists". No version
  tracking; renames, drops and data migrations aren't possible.
- **Queue**: in-memory `asyncio.Queue` + dict. A restart loses queued
  downloads and all history.

## Target

```
server/
  app/
    db/
      engine.py        SQLAlchemy engine/session (SQLite: WAL, foreign keys, busy timeout)
      models.py        ORM models for every table (incl. jobs)
      migrate.py       startup: adopt pre-Alembic databases, then upgrade to head
    repositories/      all SQL lives here; one module per aggregate
      accounts.py  books.py  settings.py  jobs.py
    services/          business rules; no HTTP, no SQL
      accounts.py  library.py  downloads.py  settings.py
    api/               HTTP only: parse, call a service, shape the response
    jobs/              the download pipeline (ffmpeg, outline, …), uses services
  migrations/          Alembic (env.py + versions/)
    versions/0001_baseline.py        today's schema, exactly
    versions/0002_jobs.py            the persistent queue
```

### Decisions

- **SQLAlchemy 2.0, synchronous**, ORM models for the tables. Queries that
  are clearer as SQL (library sorting, the FTS5 search index, which
  SQLAlchemy can't model) stay as `text()` inside the books repository.
  Sync fits how the app already works: route handlers run in FastAPI's
  threadpool and the download workers use `asyncio.to_thread`.
- **One session per request / unit of work**, committed by the service.
- **Alembic, run automatically at startup**, so `docker compose up`
  migrates. Existing databases (created before Alembic) are detected — tables
  present, no `alembic_version` — brought up to the baseline with the old
  column fixes, then stamped `0001`, and upgraded from there. Nothing is
  rebuilt or copied; data stays where it is.
- **Persistent queue**: a generic `jobs` table (a `type` column; `download`
  for now, so other background work can use it later) holds every job with its
  options and the settings snapshot it was queued with. Workers claim the
  oldest queued job; status changes are written immediately, progress
  percentages at most every few seconds (live percentages still stream over
  the WebSocket from memory).
  - After a restart, **queued jobs continue**, and **jobs that were mid-download
    are queued again** (the partial file is discarded, so they start over).
  - **History**: the most recent 500 finished jobs are kept; older ones are
    pruned at startup. The Downloads page shows history across restarts.
- **API unchanged** for the frontend, except the downloads list now
  includes finished jobs from before a restart (and gains timestamps).

## Steps (each one a commit that passes the full suite)

1. **SQLAlchemy + Alembic + repositories**: engine, models, baseline
   migration, startup migration (incl. adopting existing databases), move every
   SQL statement into repositories. No behaviour change. Verified like the Go
   port: compare every API response against the running version on a copy of
   the real database.
2. **Services**: move business logic out of routes and `library.py` into
   services; routes become thin.
3. **Persistent queue**: `0002_jobs`, queue backed by the table,
   restart recovery, history pruning, Downloads page wording.
4. **Deploy**: back up the Pi's database first, upgrade, check the migration
   adopted it, end-to-end checks (scan, PDF-only job, restart mid-queue).

## Tests to add

- Fresh database: `upgrade head` builds the same schema as the baseline.
- Pre-Alembic database with data: adopted, stamped, upgraded, data intact.
- Queue: queued jobs survive a restart; an interrupted job is re-queued;
  cancel works for persisted queued jobs; history is pruned to the limit.
