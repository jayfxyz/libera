# Plan: generic task queue, a downloads table, and an event stream

Four phases, each shippable on its own (the app works and tests pass
after each). Do 1 to 3 in order; phase 4 is independent of them.

1. **Task queue**: a generic `tasks` table, one repository, two services.
2. **Downloads**: a `downloads` table that owns everything the Downloads
   page shows; the companion PDF becomes part of every download; each
   download records a manifest of the files it wrote.
3. **Event stream**: an event bus and one HTTP stream (Server-Sent Events)
   replace the download-only WebSocket.
4. **Finding files on disk**: identify downloaded books by their Audible
   id, as Libation does, but kept in a metadata file in each book folder
   instead of in file or folder names.

## Where we are

- **`jobs` table** (`server/app/db/models.py`, migration `0002_jobs.py`) is
  both the queue and the Downloads page's data: `type` (always
  `download`), download-specific `status`
  (`queued | downloading | decrypting | done | error`), `percent`,
  `message`, `title`, `book_id`, JSON `payload`.
- **`DownloadQueue`** (`server/app/jobs/queue.py`) does three things in one
  class: enqueue, run workers (asyncio tasks in the web process, one
  `runner` function), and broadcast progress to WebSocket subscribers from
  memory.
- **`DownloadJob`** is a dataclass serialised into `jobs.payload`. It
  carries the options, a snapshot of the naming settings and the book's
  naming data.
- **Pipeline** (`server/app/jobs/download.py`): download, decrypt with
  ffmpeg, embed chapters and cover, optional chapter split, then the
  companion PDF (best-effort, behind `include_pdf`). A second path,
  `kind="pdf"`, saves only the PDF.
- **No retries.** Jobs running at shutdown are re-queued at startup and
  start over.
- **Account link is not queryable**: `jobs.book_id` points at `books`; the
  account is only inside the payload. Download state on the book lives on
  `library_books` (`liberation_status`, `last_format`, `last_downloaded`,
  `file_path`).
- **Frontend**: one WebSocket (`/ws/downloads`,
  `frontend/src/composables/useWebSocket.ts`) plus `GET /api/downloads` at
  startup. `App.vue` turns download events into library patches. There is
  no catch-up after a reconnect, and a slow client can miss the final
  event (bounded per-client queue).

## Decisions

- **Workers stay in the web process** as asyncio tasks. The enqueue side
  only writes a row; the worker only reads the table. Nothing may hold a
  direct reference from one to the other except a "wake up" nudge, so a
  separate worker process stays possible.
- **A task is not what the user sees.** The user-facing unit is a
  download. A task is the execution of work and knows nothing about books.
- **Two tasks per download, chained**: `download_book` fetches the
  encrypted file, then enqueues `decrypt_book`. A failed decrypt (often
  needing a code fix) keeps the encrypted file, so a retry doesn't
  download again or request another license. The stage is still a field
  on the download.
- **The companion PDF is part of every download.** No `kind`, no
  `include_pdf`. Fetching only the PDF remains possible, as a plain
  synchronous request that is not a download and never enters the queue.
- **The database is the source of truth; events are a best-effort
  accelerator.** A client must be able to recover by refetching.
- **Repositories follow the house style**: a module of functions taking a
  session (`repositories/tasks.py`), not a class. Services that hold state
  are classes.

---

## Phase 1: task queue

Build the queue and prove it with tests. Downloads keep running on
`DownloadQueue` until phase 2, so this phase changes no behaviour.

### Schema (migration `0003_tasks.py`, model `Task`)

```
tasks
  id            text  PK          uuid4 hex
  type          text  not null    task name, e.g. "download_book"
  payload       text  not null    JSON, validated by the task's pydantic model
  status        text  not null    pending | processing | completed | failed | cancelled
  attempts      int   not null    default 0; incremented on claim
  max_attempts  int   not null    default 1
  error         text              last failure message
  created_at    text  not null
  locked_at     text              set on claim, refreshed while running
  finished_at   text
index (status, created_at)
```

Two additions to the original sketch, both needed: `cancelled` (a
cancelled task is not a failure and must never be retried) and
`error` / `finished_at` (diagnosis and pruning).

### Task definitions (`server/app/tasks/base.py`)

```python
class BaseTask(BaseModel, Generic[P]):
    name: ClassVar[str]
    max_attempts: ClassVar[int] = 1
    payload: P

class DownloadBookPayload(BaseModel):
    download_id: str

class DownloadBook(BaseTask[DownloadBookPayload]):
    name = "download_book"
```

Phase 1 defines only `BaseTask`; `DownloadBook` arrives in phase 2. Tests
use a throwaway task type.

### Repository (`server/app/repositories/tasks.py`)

- `add(s, id, type, payload, max_attempts)`
- `claim_next(s, types)`: one atomic `UPDATE … RETURNING` (same technique
  as `repositories/jobs.py:claim_next`) that takes the oldest `pending`
  task, sets `processing`, `locked_at = now`, `attempts = attempts + 1`.
- `heartbeat(s, id)`: refresh `locked_at`.
- `complete(s, id)`, `fail(s, id, error, retry)`: `retry` puts it back to
  `pending` when `attempts < max_attempts`, else `failed`.
- `cancel(s, id)`: `pending` or `processing` to `cancelled`.
- `release_stale(s, older_than)`: `processing` tasks whose `locked_at` is
  older than the cutoff go back to `pending` **without consuming an
  attempt** (`attempts - 1`).
- `prune_finished(s, keep)`, `get(s, id)`.

### Services

- **`TaskQueueService`** (`server/app/services/task_queue.py`):
  `enqueue(task: BaseTask) -> str` validates, writes the row, nudges the
  worker; `cancel(task_id)`. It accepts an optional session so a caller
  can enqueue in the same transaction as its own writes (phase 2 needs
  this).
- **`TaskWorkerService`** (`server/app/services/task_worker.py`):
  - `register(task_cls, handler)`; a handler is
    `async def handler(payload, ctx: TaskContext) -> None`.
  - `start()` / `stop()`: N asyncio workers, as today. At startup call
    `release_stale` with a cutoff of "now" (single process: anything
    `processing` is interrupted).
  - `process()`: claim, validate the payload against the registered
    model, run the handler, then `complete` or `fail`.
  - While a handler runs, refresh `locked_at` every 30 s.
  - Failure rules: `TaskFailed(message, retry=False)` is permanent; any
    other exception retries if attempts remain. Cancellation during
    shutdown leaves the row `processing` for `release_stale`. An unknown
    `type` fails the task permanently.
  - No retry backoff. Add a `run_after` column if a task type ever needs
    one.
  - Keep the OpenTelemetry behaviour: remember the enqueuing request's
    trace context in memory by task id and attach it when the task runs.

### Wiring and tests

- Create both services in `server/app/main.py` lifespan and add them to
  `AppContext`. No handlers registered yet.
- `server/tests/test_tasks.py`: runs in order queued; two workers never
  claim the same task; retry until `max_attempts` then `failed`;
  permanent failure is not retried; cancel pending and running; stale
  `processing` tasks are released at startup without losing an attempt; a
  handler exception does not kill the worker; `stop()` cancels in-flight
  work.

---

## Phase 2: downloads

### Schema (migration `0004_downloads.py`)

```
downloads
  id               text  PK
  library_book_id  int   FK library_books.id  on delete cascade
  format           enum  not null    m4b | mp3
  split_chapters   bool  not null    default false
  path             text  not null    the book's folder (absolute): every file goes here
  base_name        text  not null    file name without extension
  status           enum  not null    queued | downloading | decrypting | done | failed | cancelled
  percent          real  not null    default 0
  error            text
  files            text              JSON manifest [{role, name, size_bytes}], names within path; written when done
  task_id          text  FK tasks.id on delete set null   the current task: download, then decrypt
  created_at, started_at, finished_at
index (status, created_at), index (library_book_id)
```

- Enums are stored as text with a CHECK constraint. `0004` also turns
  phase 1's `tasks.status` into an enum.
- `kind` and `include_pdf` do not exist. `format` describes the audio
  only. The main audio file is `path/base_name.format`.
- Where a download goes (`path`, `base_name`) is decided when it is
  queued, from the settings and the book's naming data at that moment.
  Later changes don't move a queued download, and a retry writes to the
  same place.

### Data migration (in `0004`)

- `done` jobs with `kind = audio` become `done` downloads. Their output
  path (the job's message) gives `path` and `base_name`. Resolve
  `library_book_id` from the payload's `book_id` and `account_id`; skip
  rows that no longer resolve.
- All other jobs (PDF-only, failed, cancelled, unfinished) recorded no
  output path and are dropped.
- Drop the `jobs` table.

### Code

- **`repositories/downloads.py`** and **`services/downloads.py`**
  (rewrite): `enqueue(library_book …)` writes the download and its
  `DownloadBook` task in one transaction; `enqueue_many`; `cancel`
  (download and task together); `list` (unfinished plus the newest 500
  finished, joined to the book for the title); `set_progress(download_id,
  status, percent)` with the existing "status changes now, percentages at
  most every 3 s" rule; `finish`, `fail`.
- **Duplicate rule**: enqueueing a book that already has a `queued` or
  running download returns that download; it does not create a second.
- **Handlers** (`server/app/tasks/downloads.py`, a `DownloadHandlers`
  class), thin: the pipeline in `jobs/download.py` does the work and the
  downloads service records it:
  - `download_book`: everything that needs Audible. Requests the license,
    streams the encrypted file to `.incomplete/<download_id>.<aax|aaxc>`,
    fetches the extras (cover, chapter outline, companion PDF) and writes
    what decrypting needs (`<download_id>.license.json`: format, keys,
    activation bytes) beside it: the fetched bundle. On success it
    enqueues `decrypt_book` and points `task_id` at it, in one
    transaction. `max_attempts = 3`: network errors retry; a refused
    license doesn't.
  - `decrypt_book`: local only, no network. ffmpeg with chapters and
    cover embedded, move into place, extras next to it, optional split,
    manifest, done. `max_attempts = 1`. On success it deletes the bundle;
    on failure it keeps it.
- **Retry**: `POST /api/downloads/{id}/retry` on a `failed` download. If
  its encrypted file and keys are still there, enqueue `decrypt_book`
  only; otherwise `download_book`. Same download row (status back to
  `queued`, error cleared). A "Retry" button on failed downloads in
  `DownloadsView.vue`.
- **Kept encrypted files** are deleted when the download is cancelled or
  decrypted, and at startup when older than 7 days (a retry after that
  downloads again).
- **Reconcile at startup**: a download that is `queued`, `downloading` or
  `decrypting` with no live task (`task_id` null, or the task is
  `failed` / `cancelled` / `completed`) becomes `failed`.
- **`library_books`** keeps `liberation_status`, `last_format`,
  `last_downloaded` and `file_path` as a cache for library filtering.
  Update them in the same transaction that finishes or fails the
  download. Library rescan is unchanged.
- **Progress broadcast**: move `subscribe` / `unsubscribe` / `_emit` out
  of `DownloadQueue` into a small class unchanged, so the WebSocket keeps
  working until phase 3.
- Delete `jobs/queue.py`, `repositories/jobs.py`, the `Job` model and
  `_process_pdf_only` (replaced by the synchronous PDF endpoint below).

### Companion PDF

- Every download fetches the PDF after the audio is in place. It stays
  best-effort: a title without a PDF, or a failed fetch, does not fail
  the download (log a warning).
- When saved, it is an entry with `role = pdf` in the download's `files`.
- Remove from the API and frontend: `kind`, `include_pdf`, the
  include-PDF option (`BookPanel.vue`), the PDF chip and "Saved" label
  (`DownloadsView.vue`), `JobKind` (`api/client.ts`) and the `kind`
  filters in `stores/downloads.ts` and `App.vue`.

### Knowing whether a book has a PDF

Audible's library listing reports it: with `pdf_url` added to the
response groups, each item has a `pdf_url` (checked against the live
accounts: 9 of 43 titles have one).

- Add `pdf_url` to `RESPONSE_GROUPS` in
  `server/app/audible_api/library.py` and a `has_pdf` boolean to
  `normalize_item`.
- New nullable column `books.has_pdf` (in migration `0004`), written by
  the library sync. Null means "not synced since this change".
- Return `has_pdf` from the library list and book detail endpoints.
- The download handler skips the PDF step when `has_pdf` is false, and
  still tries when it is null.
- Store only the flag, not the URL: the URL is fetched fresh when
  needed.

### PDF on its own (synchronous)

For a book that is already downloaded, or when only the PDF is wanted.
The option is shown only for books where `has_pdf` is true: the "PDF
only" buttons are hidden otherwise, and the bulk action applies only to
the selected books that have one. Until the next library sync no book
has the flag, so the option is hidden for all.

- **`POST /api/library/{book_id}/pdf`** (optional `account_id`, resolved
  like a download). The request fetches the PDF from Audible, writes it
  into the book's folder and returns when done: `200 {"file_path": …}`,
  `404` if the title has no companion PDF, `502` with the reason if
  Audible fails. No task, no `downloads` row, nothing on the Downloads
  page.
- Destination: next to the audio file when its location is known
  (`library_books.file_path`: same folder, same base name, `.pdf`).
  Otherwise the folder and file name the current settings would give
  (the same naming as a download, `_paths` in today's
  `jobs/download.py`).
- If the book has a `done` download, add or replace that download's
  `role = pdf` entry in its `files`, so the manifest stays true.
  Otherwise just write the file.
- Logic lives in the downloads service (reusing the PDF step of the
  handler); the route only maps errors to status codes.
- Frontend: the "PDF only" buttons (`BookPanel.vue`) call this endpoint
  and show a busy state, then a success or error message in place. The
  bulk PDF action (`LibraryView.vue`, around line 404) calls it once per
  selected book, one at a time, and reports how many were saved, had no
  PDF, or failed.
- Replace `_process_pdf_only` and its two tests with tests for this
  endpoint: saves the PDF without requesting a license; `404` when there
  is none; updates the manifest of an existing download.

### Manifest

- After all files are in their final place, record every file the
  download wrote in its `files` column (JSON: role, file name within the
  download's `path`, size). This is the
  record of what a download produced, which `library_books.file_path`
  (one path) cannot express.
- No content hashes: other tools (Audiobookshelf, tag editors) rewrite
  the files, so a hash could only ever say "modified since download".
- Writing the manifest is non-fatal: on failure the download is still
  `done`.

### API and frontend

- `POST /api/downloads` and `/bulk` drop `kind` and `include_pdf`.
  Responses and events keep the `job_id` field name (its value is the
  download id) until phase 3 reshapes events.
- Statuses change from `error` to `failed` and `cancelled`; update
  `frontend/src/lib/bookStatus.ts`, `DownloadsView.vue` and the client
  types.

### Tests

- Port `test_queue.py` cases that are about downloads (history pruning,
  progress save interval, survive restart, cancel) to the downloads
  service; the generic ones are already covered by `test_tasks.py`.
- Update `test_download_job.py`: move the PDF-only tests to the new
  endpoint; assert the
  PDF is saved by default, that a missing PDF doesn't fail the download,
  that `files` is written and matches the files on disk; that a failed
  decrypt keeps the encrypted file and a retry decrypts it without
  downloading again; that `download_book` retries a network error; and
  that kept files older than 7 days are removed at startup.
- A migration test: a database at `0002` with finished, PDF-only and
  queued jobs upgrades to the expected `downloads` rows.

---

## Phase 3: event stream

### Server

- **`EventBus`** (`server/app/events.py`): `publish(type, id, data)` and
  `subscribe()`. In-memory implementation; the interface is the seam for
  a separate worker process later.
  - `publish` must be safe to call from worker threads
    (`loop.call_soon_threadsafe`).
  - Each subscription keeps **the latest event per `(type, id)`**, not a
    FIFO queue, so a slow client skips intermediate percentages but never
    misses a final state.
- **Events carry the whole resource**, in the same shape as its REST
  representation:
  `{"type": "download.updated", "id": "…", "data": { …download… }}`.
  Types: `download.updated`, `book.updated`.
- **Publishers**: the downloads service after each status or progress
  write; the library service when a book's download state changes
  (replacing the inference in `App.vue`). Progress is limited to about two
  events a second per download.
- **`GET /api/events`**: `text/event-stream`, one SSE message per event,
  a comment line every 15 s as keep-alive, `Cache-Control: no-cache` and
  `X-Accel-Buffering: no`. `GZipMiddleware` buffered the stream, so it
  now wraps only the static frontend mount; API responses, the stream
  included, are not compressed.
- **`updated_at`** (migration `0005_updated_at.py`) on `downloads` and
  `library_books`, set by every write. A snapshot and an event can cross
  (a reconnect while a reload is in flight), so clients keep the copy with
  the later `updated_at`. `book.updated` is published only for
  download-state changes; other edits still bump the stamp.
- Remove the WebSocket routes, `download_progress` and the broadcaster
  class from phase 2.

### Frontend

- `useEventStream` (replaces `useWebSocket.ts`): one `EventSource` for
  the app; `on(type, handler)` and `onOpen(handler)`.
- Stores subscribe by type: `download.updated` upserts into the downloads
  store, `book.updated` into the library store.
- **On every open, including reconnects, each store reloads its
  snapshot.** This is the catch-up mechanism; there is no event replay.
- `job_id` becomes `id` across the API (responses, the bulk endpoint's
  `{"downloads": [...]}`, path parameters) and in the downloads store and
  views, to match the resource shape.

### Tests

- Bus: latest-per-key coalescing; a final event is delivered to a
  subscriber that stopped reading; publish from a thread.
- Endpoint: a client receives `download.updated` events for a running
  download and a `book.updated` when it finishes.

---

## Phase 4: finding files on disk

### Today

- `rescan` (`server/app/services/library.py`) marks a book downloaded when
  some `.m4b` / `.mp3` file's name equals the sanitised title. It breaks
  with any filename template other than the bare title, can't tell
  editions apart, and doesn't record where the file is (in the live
  database all downloaded books have `file_path` null).
- Nothing notices a file that was moved or deleted.

### How Libation does it

From Libation's source (`AudibleFileStorage.cs`) and docs:

- **Identity is the Audible id (ASIN), never the title.** "The Audible id
  must be somewhere in the book's file or folder name for Libation to
  detect your downloaded book."
- **Lookup is cache, then search.** A path cache maps id to file path. A
  cached path is used only if the file still exists; otherwise Libation
  searches an in-memory index of the books folder for a path that
  contains the id and ends in an audio extension, and caches the hit.
- **"Locate Audiobooks"** scans a folder the user picks, reads the id
  from each file (Libation uses the audio tags), and adds what it finds
  to the cache and the library.
- **Downloaded status is the user's to set.** It is stored, not derived
  from the disk, and can be changed by hand. A missing file does not
  silently flip it.

### Where we differ from Libation: a metadata file, not names

Libation puts the id in file and folder names. We don't: names stay
exactly what the templates produce, and the id lives in a metadata file
inside the book's folder. No `{asin}` template tag, no id in audio tags.

### One book per folder

The metadata file describes one book, so a folder must hold exactly one
book. The folder template stops being free text and becomes a choice of
two:

- `{author} - {title}` (the default)
- `{title} - {author}`

What changes:

- **Server**: validate `folder_template` against these two in the
  settings service and reject anything else; `book_directory`
  (`server/app/jobs/filename.py`) no longer accepts a blank template.
- **Migration**: a saved `folder_template` that is neither value is
  reset to the default. Files already downloaded stay where they are;
  only new downloads use the new folder.
- **Frontend** (`SettingsView.vue`): the folder field becomes a select
  with a preview; the tag picker applies to the file name only.
- The file name template stays free text.
- **Same folder, different book**: two titles can still render to the
  same folder (two editions with the same author and title). If the
  target folder already has a `libation.json` for a different ASIN, the
  download appends the release year, e.g.
  `Jordan Peterson - 12 Rules for Life (2018)`. If the year is unknown
  or that folder is also taken by another book, append ` (2)` (then
  ` (3)`, …) instead.

**`libation.json`**, one per book folder, written by every download:

```json
{
  "version": 1,
  "asin": "B078Y7X7M4",
  "title": "12 Rules for Life",
  "format": "m4b",
  "downloaded_at": "2026-11-12T10:15:00Z",
  "files": [
    {"role": "audio", "name": "12 Rules for Life.m4b", "size_bytes": 512000000},
    {"role": "pdf", "name": "12 Rules for Life.pdf", "size_bytes": 2400000}
  ]
}
```

- **`files` is the phase 2 manifest** (`downloads.files`), with file
  names within the folder. The file on disk and the table say the same
  thing.
- **Not `metadata.json`**: Audiobookshelf reads and writes a file of that
  name in each book folder with its own schema.
- **No account details** in the file: it travels with the folder.
- **Writing**: write to a temporary file and rename. Re-downloading a
  book replaces the file. A write failure is logged and does not fail
  the download.
- The standalone PDF endpoint updates the file too.
- `.chapters.json` is unchanged: it stays the chapter sidecar, written
  only when Audible's outline is available.

### Locator (`server/app/services/locator.py`)

`find(book) -> path | None`, in this order:

1. `library_books.file_path`, if that file exists. This column is the
   path cache.
2. An in-memory index of ASIN to folder, built by one walk of the
   audiobooks folder that reads every `libation.json` (hidden folders
   skipped, as today). Rebuilt by a scan and updated after each download.
   The path is the folder joined with the entry's `audio` file; if that
   file is gone (renamed), any single `.m4b` / `.mp3` in the folder.
3. Not found.

A hit from step 2 is written back to `file_path`. For a download split
into chapter files, the located path is the book's folder.

Consequence to state in the UI help: moving or renaming a book's
**folder** is always followed; moving the audio file out of its folder
on its own is not.

### Scan ("Locate audiobooks")

Replaces today's rescan behind the same endpoint
(`POST /api/library/rescan`), with an optional folder to scan instead of
the whole audiobooks folder (it must be inside a folder the container
has mounted; reject anything else).

Matching, first that yields a known ASIN wins:

1. a `libation.json` in the folder;
2. a `.chapters.json` next to an audio file (downloads from before this
   phase have one, and it contains the ASIN);
3. today's title match, as the last resort for anything older.

A match records `file_path` and marks the book downloaded. **For matches
from 2 and 3 the scan writes a `libation.json`**, so existing downloads
are adopted on the first scan and found by method 1 from then on. The
scan assumes one book per folder; folders holding several books (from a
blank or custom folder template in older versions) are not supported.
The
response reports how many books were matched by each method and how
many audio files matched nothing.

### Missing files and manual status

- No automatic un-marking. When a downloaded book's file can't be found,
  the book panel says so ("file not found") and offers "Locate" (run the
  locator again) and "Mark as not downloaded".
- Manual status: allow `liberation_status` in
  `PATCH /api/library/{book_id}` and the bulk update, with "Mark as
  downloaded" / "Mark as not downloaded" actions in the UI.
- The standalone PDF endpoint (phase 2) uses the locator for its
  destination.

### Tests

- A download writes `libation.json`; re-downloading replaces it; a
  different book that renders to the same folder name gets the year
  appended, or ` (2)` when the year is unknown or also taken.
- Settings reject a folder template other than the two allowed; the
  migration resets a custom one to the default.
- Lookup: recorded path wins; a renamed or moved folder is found again
  through its `libation.json`; the hit is written back; a renamed audio
  file inside the folder is still found.
- Scan: matches by metadata file, by `.chapters.json` and by title;
  writes `libation.json` for the latter two; reports unmatched files.
- Manual status change survives a scan.

---

## Out of scope

- A separate worker process.
- Resuming a partial download (checkpointing) and retry backoff.
- Per-topic event subscriptions and event replay.

## Checks for every phase

- `docker build --target test -t libation-web-test . && docker run --rm libation-web-test`
- `cd frontend && npm run type-check && npm run lint`
- Upgrade a copy of a real database (`data/db/libation.db`) and confirm
  the Downloads page still shows its history.
