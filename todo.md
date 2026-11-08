# Libation Web — Feature Parity Todo

Features ranked by value added on top of a bare library viewer.
`[x]` = fully implemented · `[~]` = partial / stub · `[ ]` = not started

**Decisions recorded (from interview):**
- MP3: global default in Settings + per-download override
- Widevine: skipped (show error if title is Widevine-only)
- Advanced search syntax: skipped — simple FTS keyword search is enough
- File naming: configurable templates with tags like `{author}`, `{title}`, etc.
- Chapter splitting: yes, as a user option
- PDF download: yes, automatic when available
- Export: yes (CSV + JSON)
- Settings persistence: SQLite DB
- Tag editing: inline chip input in book detail panel
- Inactive book detection: yes, mark flagged books visually
- Quick filters (saved searches): skipped for now

---

## Tier 1 — Core loop (nothing works without these)

- [x] **Multi-account management** — CRUD for accounts; locales US/UK/CA/DE/FR/AU/JP/IN/ES; nickname editing; per-account last-scan timestamp; library-scan toggle stored in DB
  - `server/app/api/accounts.py`, `server/app/schema.sql`
  - Frontend: `frontend/src/views/AccountsView.vue`, `frontend/src/stores/accounts.ts`

- [x] **Audible authentication** — browser-based 2-step OAuth (maplanding URL flow); code verifier + device serial; iOS User-Agent header patch for CloudFront; token persistence per account
  - `server/app/audible_api/auth.py`, `server/app/audible_api/storage.py`
  - Routes: `server/app/api/accounts.py` → `auth_start` / `auth_complete`

- [x] **Library scan / import** — per-account Audible API fetch; upserts books, contributors, series; FTS5 index maintained in same transaction; `last_scanned_at` updated
  - `server/app/audible_api/library.py`, `server/app/library.py` → `import_library`

- [x] **Book metadata model** — books (title, subtitle, description, length_minutes, cover_url, publisher, audible_rating, abridged, spatial, content_type, language); library_books (liberation_status, tags, user_rating, is_finished, date_added, is_audible_plus, last_format); contributors + roles; series + position; categories
  - `server/app/schema.sql`

- [x] **Download & DRM decryption** — AAXC preferred, AAX fallback; license/voucher acquisition; streaming download with progress; ffmpeg decryption; file size sanity check; liberation_status updated on success
  - `server/app/audible_api/content.py`, `server/app/jobs/download.py`

- [x] **Output format: M4B vs MP3** — default format setting persisted in DB and shown in Settings UI; per-download format picker in detail panel (inherits default); ffmpeg re-encodes with `libmp3lame -q:a 2` for MP3, `-c:a copy` for M4B.
  - `server/app/jobs/download.py`, `server/app/jobs/ffmpeg.py`, `server/app/api/settings.py`, `frontend/src/views/SettingsView.vue`, `frontend/src/components/library/BookDetailPanel.vue`

- [x] **PDF attachment download** — after audio decryption succeeds, the job fetches the companion-file URL with the authenticated Audible client and saves the PDF next to the audio; best-effort (failure is logged, not surfaced to the user).
  - `server/app/audible_api/content.py`, `server/app/audible_api/client.py` → `get_pdf`, `server/app/jobs/download.py`

- [x] **Inactive book detection** — during each scan, books absent from the new ASIN list are marked `is_deleted=1`; books that reappear are restored to `is_deleted=0`. UI shows dimmed card + "Removed from Audible" badge; a "Removed" filter pill appears when there are any removed books.
  - `server/app/library.py` → `import_library`; `server/tests/test_library.py`; `frontend/src/components/library/BookCard.vue`, `frontend/src/stores/library.ts`, `frontend/src/views/LibraryView.vue`

---

## Tier 2 — Library usability (makes the tool worth using daily)

- [x] **Full-text search** — SQLite FTS5 on title, subtitle, description, authors, narrators, series_name, tags; debounced search input in UI. Simple keyword search only (no advanced syntax — decided to skip Lucene-style operators).
  - `server/app/library.py` → `list_books`; `frontend/src/views/LibraryView.vue`

- [x] **Status filter pills** — All / Downloaded / Not Downloaded / In Progress — applied client-side
  - `frontend/src/views/LibraryView.vue`, `frontend/src/stores/library.ts`

- [x] **User tagging (display)** — tags stored as space-separated string; shown as chips in BookCard and BookDetailPanel; FTS5 indexes the tags field

- [x] **Tag editing (inline chip input)** — editable chips in BookDetailPanel: `×` removes a tag, `+ tag` opens an inline input (Enter commits, Escape cancels). Each change PATCHes the API and syncs the library store immediately.
  - `frontend/src/components/library/BookDetailPanel.vue`

- [x] **Download queue with worker pool** — configurable worker count; job state map; `GET /downloads` lists all jobs
  - `server/app/jobs/queue.py`

- [x] **Download cancellation** — `DELETE /downloads/{id}` cancels a running job's task (stopping the download and killing ffmpeg) or drops a queued one. Returns 404 if the job is neither running nor queued.
  - `server/app/jobs/queue.py` → `cancel`; `server/app/jobs/download.py`; `server/app/api/downloads.py`

- [x] **Real-time download progress via WebSocket** — progress events broadcast to every subscriber; Vue composable with auto-reconnect
  - `server/app/api/downloads.py`, `frontend/src/composables/useWebSocket.ts`

- [x] **Per-book download status badges** — color-coded in BookCard and BookDetailPanel

- [x] **Configurable file naming templates** — tags: `{title}` `{author}` `{narrator}` `{series}` `{series_index}` `{year}` `{language}` `{duration_h}`. Empty tags are stripped with their surrounding separators. Persisted in DB, shown in Settings UI. Defaults to `{title}`.
  - `server/app/jobs/filename.py`, `server/app/config.py`, `server/app/api/settings.py`, `frontend/src/views/SettingsView.vue`

- [x] **Settings persistence** — `settings` table in SQLite (`server/app/db.py`); saved values overlay the env defaults at startup (`Config.apply_overrides`); `PATCH /settings` writes to the DB and updates the in-memory config. Tests in `server/tests/test_settings.py`.
  - Note: `app_url` field shown in the Settings UI is not yet saved by `PATCH /settings` (not a persisted setting)

---

## Tier 3 — Power-user features

- [~] **Locate existing audiobooks** — `POST /library/rescan` walks the output directory, including per-book folders (hidden ones skipped), and matches audio files to books by sanitised title. Files named with a custom template that doesn't start from `{title}` aren't matched.
  - `server/app/library.py` → `rescan`

- [x] **Chapter splitting** — "Chapters" checkbox in the detail panel; when checked, the job probes the decrypted file with ffprobe and extracts each chapter to a separate file (non-fatal if no chapters found). Chapter files use the filename template as a base.
  - `server/app/jobs/chapters.py`, `server/app/jobs/download.py`, `frontend/src/components/library/BookDetailPanel.vue`

- [x] **Audible chapter outline** — Audible's real chapter titles and timings (nested parts flattened as Libation does) are embedded in the audio during decryption, with `<book>.cue` and `<book>.chapters.json` written alongside.
  - `server/app/jobs/outline.py`, `server/app/audible_api/content.py` → `get_chapter_info`

- [x] **Per-book folders** — each book's audio, chapter files and PDF go in a folder named by the "Book folder" template (default `{author} - {title}`).
  - `server/app/jobs/filename.py` → `book_directory`, `frontend/src/views/SettingsView.vue`

- [x] **Library sorting** — title, author, date added, release date, length, series, Audible rating, recently downloaded; both directions; remembered per browser.
  - `server/app/library.py` → `SORTS`, `frontend/src/views/LibraryView.vue`, `frontend/src/stores/library.ts`

- [x] **Library export** — `GET /api/library/export?format=csv|json` returns a denormalized export of all non-deleted books (authors, narrators, series, tags, ratings, status). CSV and JSON download buttons in the Library header.
  - `server/app/library.py`, `frontend/src/views/LibraryView.vue`

- [x] **"Is finished" toggle** — toggle switch in BookDetailPanel metadata section PATCHes `is_finished` and syncs the library store.
  - `frontend/src/components/library/BookDetailPanel.vue`

- [x] **User rating** — 5-star rating widget in BookDetailPanel; clicking the active star clears the rating.
  - `frontend/src/components/library/BookDetailPanel.vue`

---

## Tier 4 — CLI & automation

- [ ] **CLI: scan** — no CLI; all operations are web-only
- [ ] **CLI: liberate** — no CLI
- [ ] **CLI: convert** — no CLI
- [ ] **CLI: export** — no CLI

---

## Tier 5 — Polish & operations

- [ ] **Automatic periodic library scan** — no background scheduler; scan is manual per-account

- [x] **OpenTelemetry tracing** — optional OTLP export (set `OTEL_EXPORTER_OTLP_ENDPOINT`); FastAPI and httpx instrumented; a download is one trace: request → `job.enqueue` → `job.process` → Audible calls, `job.download`, `job.chapters`, `job.ffmpeg`
  - `server/app/telemetry.py`, `server/app/jobs/download.py`

- [ ] **Slimmer Docker image** — the image is 671 MB, mostly Debian's `ffmpeg` package and its codec libraries. A minimal ffmpeg (only the mov/mp4 demuxer with Audible decryption, the AAC copy path and LAME for MP3), e.g. a static build copied in, would cut it substantially. Keep `python:3.12-slim-trixie` for SQLite >= 3.43.
  - `Dockerfile`

- [ ] **Activation bytes caching** — `get_activation_bytes(extract=True)` called on every AAX download; no caching; slow and potentially rate-limited by Audible
  - `server/app/audible_api/content.py` → `_activation_bytes`

- [ ] **Search syntax help** — no in-app reference for what FTS5 accepts

- ~~Widevine DRM~~ — skipped; show an error message if a title can only be downloaded in Widevine format
- ~~Advanced search syntax~~ — skipped; simple FTS keyword search is sufficient
- ~~Quick filters (saved searches)~~ — skipped for now; status pills cover the main use cases

---

## Test coverage checklist

All in `server/tests/` (run in the shipping base image; see the plan doc).

- [x] Account CRUD + login flow — `test_api_accounts_downloads.py`, `test_audible_api.py`
- [x] Library import (upsert idempotency, inactive book detection, per-account) — `test_library.py`
- [x] Download job — AAX path with real ffmpeg, MP3 re-encode, chapters embedded, chapter split, license-denial and error handling — `test_download_job.py`
- [ ] Download job — AAXC decryption with a real AAXC file (needs a fixture file)
- [x] File naming template rendering — all tags, missing values, unsafe characters — `test_filename.py`
- [x] Settings persistence round-trip — `test_settings.py`
- [x] Rescan files — `test_library.py`, `test_library_api.py`
- [x] Export — CSV and JSON — `test_library_api.py`
- [x] Serving the frontend (cache headers, fallback, gzip) — `test_static.py`
