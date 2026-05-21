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
  - `backend/internal/api/accounts.go`, `backend/internal/db/schema.sql`
  - Frontend: `frontend/src/views/AccountsView.vue`, `frontend/src/stores/accounts.ts`

- [x] **Audible authentication** — browser-based 2-step OAuth (maplanding URL flow); code verifier + device serial; iOS User-Agent header patch for CloudFront; token persistence per account
  - `audible-svc/routes/auth.py`, `audible-svc/storage.py`
  - Backend relay: `backend/internal/api/accounts.go` → `authStart` / `authComplete`

- [x] **Library scan / import** — per-account Audible API fetch; upserts books, contributors, series; FTS5 index maintained in same transaction; `last_scanned_at` updated
  - `audible-svc/routes/library.py`, `backend/internal/api/library.go` → `importLibrary`

- [x] **Book metadata model** — books (title, subtitle, description, length_minutes, cover_url, publisher, audible_rating, abridged, spatial, content_type, language); library_books (liberation_status, tags, user_rating, is_finished, date_added, is_audible_plus, last_format); contributors + roles; series + position; categories
  - `backend/internal/db/schema.sql`, `backend/internal/domain/book.go`

- [x] **Download & DRM decryption** — AAXC preferred, AAX fallback; license/voucher acquisition; streaming download with progress; ffmpeg decryption; file size sanity check; liberation_status updated on success
  - `audible-svc/routes/download.py`, `backend/internal/jobs/download.go`

- [x] **Output format: M4B vs MP3** — default format setting persisted in DB and shown in Settings UI; per-download format picker in detail panel (inherits default); ffmpeg re-encodes with `libmp3lame -q:a 2` for MP3, `-c:a copy` for M4B.
  - `backend/internal/jobs/download.go`, `backend/internal/jobs/ffmpeg.go`, `backend/internal/api/settings.go`, `frontend/src/views/SettingsView.vue`, `frontend/src/components/library/BookDetailPanel.vue`

- [x] **PDF attachment download** — audible-svc `GET /download/{account_id}/{asin}/pdf` fetches the companion-file URL via the authenticated Python client and streams it back. After audio decryption succeeds, the job attempts a best-effort PDF download (failure is logged, not surfaced to the user).
  - `audible-svc/routes/download.py`, `backend/internal/audible/client.go` → `DownloadPDF`, `backend/internal/jobs/download.go`

- [x] **Inactive book detection** — during each scan, books absent from the new ASIN list are marked `is_deleted=1`; books that reappear are restored to `is_deleted=0`. UI shows dimmed card + "Removed from Audible" badge; a "Removed" filter pill appears when there are any removed books.
  - `backend/internal/api/library.go` → `importLibrary`; `backend/internal/api/library_test.go`; `frontend/src/components/library/BookCard.vue`, `frontend/src/stores/library.ts`, `frontend/src/views/LibraryView.vue`

---

## Tier 2 — Library usability (makes the tool worth using daily)

- [x] **Full-text search** — SQLite FTS5 on title, subtitle, description, authors, narrators, series_name, tags; debounced search input in UI. Simple keyword search only (no advanced syntax — decided to skip Lucene-style operators).
  - `backend/internal/api/library.go` → `listLibrary`; `frontend/src/views/LibraryView.vue`

- [x] **Status filter pills** — All / Downloaded / Not Downloaded / In Progress — applied client-side
  - `frontend/src/views/LibraryView.vue`, `frontend/src/stores/library.ts`

- [x] **User tagging (display)** — tags stored as space-separated string; shown as chips in BookCard and BookDetailPanel; FTS5 indexes the tags field

- [x] **Tag editing (inline chip input)** — editable chips in BookDetailPanel: `×` removes a tag, `+ tag` opens an inline input (Enter commits, Escape cancels). Each change PATCHes the API and syncs the library store immediately.
  - `frontend/src/components/library/BookDetailPanel.vue`

- [x] **Download queue with worker pool** — configurable worker count; job state map; `GET /downloads` lists all jobs
  - `backend/internal/jobs/queue.go`

- [x] **Download cancellation** — each in-flight job registers a `context.CancelFunc` by job ID; `DELETE /downloads/{id}` calls it, propagating cancellation to the streaming download and ffmpeg process. Returns 404 if the job is not running.
  - `backend/internal/jobs/queue.go` → `Cancel/registerCancel/deregisterCancel`; `backend/internal/jobs/download.go`; `backend/internal/api/downloads.go`

- [x] **Real-time download progress via WebSocket** — `ProgressEvent` fan-out; Vue composable with auto-reconnect
  - `backend/internal/api/ws.go`, `frontend/src/composables/useWebSocket.ts`

- [x] **Per-book download status badges** — color-coded in BookCard and BookDetailPanel

- [ ] **Configurable file naming templates** — current output is `sanitizeFilename(title).ext` with no customization. Need:
  1. A template engine supporting tags: `{title}`, `{author}`, `{narrator}`, `{series}`, `{series_index}`, `{year}`, `{language}`, `{duration_h}`
  2. Separate templates for: folder path and filename (e.g. `{author}/{series}/{title}`)
  3. Settings UI to define and preview templates
  4. Template rendering in `backend/internal/jobs/download.go` before writing the output file
  - Replaces hardcoded `sanitizeFilename` in `backend/internal/jobs/download.go` and `backend/internal/api/library.go`

- [x] **Settings persistence** — `settings` table in SQLite; `GetSetting`/`SetSetting`/`LoadAllSettings` in `backend/internal/db/settings.go`; DB overrides applied to `Config` at startup via `ApplyDBOverrides`; `PATCH /settings` writes to DB and updates in-memory config atomically (RWMutex). Tests in `backend/internal/db/settings_test.go`.
  - Note: `app_url` field shown in the Settings UI is not yet saved by `PATCH /settings` (not a persisted setting)

---

## Tier 3 — Power-user features

- [~] **Locate existing audiobooks** — `POST /library/rescan` scans OutputDir and matches by filename; works for the happy path but filename matching is fragile (different sanitization in API vs jobs layer, and no folder traversal). Needs alignment once file naming templates are implemented.
  - `backend/internal/api/library.go` → `rescanFiles`

- [ ] **Chapter splitting** — user option at download time to split into one file per chapter. Need:
  1. Download option: "Split into chapters" checkbox (alongside format picker)
  2. Backend: after decryption, use `ffmpeg -i` to read chapter metadata, then re-encode each chapter to a separate file with chapter-aware naming (e.g. `{title} - Ch{n} - {chapter_title}.m4b`)
  3. Progress reporting for multi-file output
  - `backend/internal/jobs/download.go`

- [ ] **Library export** — no export endpoint. Need:
  1. `GET /library/export?format=csv` and `?format=json` endpoints
  2. Download button in the UI (Settings page or Library header)
  - `backend/internal/api/library.go`

- [ ] **"Is finished" toggle** — `library_books.is_finished` exists and is patchable via API, but there is no UI control to toggle it in BookDetailPanel

- [ ] **User rating** — `library_books.user_rating` exists and is patchable via API, but there is no UI control in BookDetailPanel (only Audible's community rating is displayed)

---

## Tier 4 — CLI & automation

- [ ] **CLI: scan** — no CLI; all operations are web-only
- [ ] **CLI: liberate** — no CLI
- [ ] **CLI: convert** — no CLI
- [ ] **CLI: export** — no CLI

---

## Tier 5 — Polish & operations

- [ ] **Automatic periodic library scan** — no background scheduler; scan is manual per-account

- [x] **OpenTelemetry tracing** — OTLP/Jaeger distributed tracing; W3C trace-context propagated into worker goroutines; spans for enqueue, download, ffmpeg
  - `backend/internal/telemetry/telemetry.go`, `audible-svc/main.py`

- [ ] **Activation bytes caching** — `get_activation_bytes(extract=True)` called on every AAX download; no caching; slow and potentially rate-limited by Audible
  - `audible-svc/routes/download.py` → `_get_activation_bytes`

- [ ] **Search syntax help** — no in-app reference for what FTS5 accepts

- ~~Widevine DRM~~ — skipped; show an error message if a title can only be downloaded in Widevine format
- ~~Advanced search syntax~~ — skipped; simple FTS keyword search is sufficient
- ~~Quick filters (saved searches)~~ — skipped for now; status pills cover the main use cases

---

## Test coverage checklist

- [ ] Account CRUD + OAuth flow (multi-account, token persistence)
- [ ] Library import (upsert idempotency, FTS index consistency, inactive book detection)
- [ ] Download job — AAXC path, AAX fallback, MP3 re-encode, chapter split, error handling
- [ ] File naming template rendering — all tags, edge cases (missing series, special chars)
- [ ] Settings persistence round-trip (write to DB, reload on startup)
- [ ] Rescan files — filename matching edge cases
- [ ] Export — CSV and JSON output correctness
- [x] `audible-svc/tests/test_auth.py` — auth register/callback
- [x] `audible-svc/tests/test_library.py` — library normalization
