# Plan: Audiobook Player

## Context
Add in-app playback for downloaded (liberated) audiobooks. Files are stored locally as `.m4b` or `.mp3` on the Go backend server. There is no existing audio playback code. The player should be a persistent bottom bar (Spotify-style) with chapter navigation, resume position, playback speed, and skip forward/back.

---

## Architecture Overview

**Backend** serves audio via HTTP range requests (required for browser seeking) and extracts chapter metadata via `ffprobe`. Playback position is persisted to the existing `library_books` table.

**Frontend** uses an HTML `<audio>` element (managed in a Pinia store) with a new persistent `PlayerBar.vue` component mounted globally in `App.vue`.

---

## Backend Changes

### 1. Database migration
Add two columns to `library_books` in `backend/internal/db/schema.sql`:
```sql
ALTER TABLE library_books ADD COLUMN file_path TEXT;
ALTER TABLE library_books ADD COLUMN playback_position_ms INTEGER DEFAULT 0;
```
`file_path` is populated when a download completes, and updated by `/api/library/rescan`.

### 2. Save file path after download
In `backend/internal/jobs/download.go`, after the file is written, `UPDATE library_books SET file_path=?, last_format=?, liberation_status='liberated' WHERE ...`.

### 3. New API endpoints — `backend/internal/api/library.go`

**`GET /api/library/{id}/stream`**
- Look up `file_path` from `library_books` (must be `liberated`)
- Serve file with `http.ServeContent(w, r, filename, modTime, f)` — this handles Range headers automatically, enabling browser seeking
- Return 404 if file not found, 409 if not liberated

**`GET /api/library/{id}/chapters`**
- Run `ffprobe -v quiet -print_format json -show_chapters {file_path}`
- Parse JSON and return array: `[{ title, start_ms, end_ms }]`
- Return empty array (not error) for mp3 files or m4b files without chapters

**Extend `PATCH /api/library/{id}`** — already exists; add `playback_position_ms int` to the patch body struct.

### 4. Register routes — `backend/internal/api/router.go`
```go
r.Get("/library/{id}/stream", h.StreamBook)
r.Get("/library/{id}/chapters", h.GetBookChapters)
```

---

## Frontend Changes

### 5. API client — `frontend/src/api/client.ts`
Add:
```typescript
getChapters(id: number): Promise<Chapter[]>   // GET /api/library/{id}/chapters
// streaming URL is just a string: `/api/library/${id}/stream`
// PATCH /api/library/{id} already exists; extend its payload type to include playback_position_ms
```

### 6. Player store — `frontend/src/stores/player.ts` (new)
Pinia store owns the `<audio>` element instance and all state:
```typescript
interface Chapter { title: string; start_ms: number; end_ms: number }
interface PlayerStore {
  bookId: number | null
  book: LibraryBook | null
  chapters: Chapter[]
  isPlaying: boolean
  currentTime: number     // seconds, updated on timeupdate
  duration: number        // seconds
  speed: number           // 1.0 default
  volume: number          // 0–1
}
```
Key actions:
- `play(book)` — sets audio src to `/api/library/{id}/stream`, fetches chapters, seeks to persisted `playback_position_ms / 1000`, begins playback
- `seek(seconds)` — sets `audio.currentTime`
- `setSpeed(rate)` — sets `audio.playbackRate`
- `skipForward()` / `skipBack()` — `±30` seconds
- Listens to `timeupdate` — saves position to API every 5 seconds
- `currentChapter` computed — finds chapter by `currentTime`

### 7. PlayerBar component — `frontend/src/components/shared/PlayerBar.vue` (new)
Persistent bottom bar, only rendered when `playerStore.bookId != null`:
```
[cover thumbnail]  [title / chapter name]    [<<30] [play/pause] [30>>]    [scrubber ── time/total]    [speed] [volume]
```
- Scrubber: use existing `<Progress>` or a range input for seeking (shadcn `Slider` in `src/components/ui/` if available)
- Speed: dropdown or cycle button (0.75 → 1 → 1.25 → 1.5 → 1.75 → 2)
- Chapter display: shows current chapter title (from `currentChapter` computed)
- Clicking cover/title navigates to library and opens that book's detail panel

### 8. App.vue — `frontend/src/App.vue`
- Import and render `<PlayerBar />` below the main router view
- Add conditional `pb-24` bottom padding to the main content area when player is active (so content doesn't hide behind the bar)

### 9. BookDetailPanel — `frontend/src/components/library/BookDetailPanel.vue`
For books where `liberation_status === 'liberated'`:
- Add a **"Play"** button alongside the "Re-download" button
- Calls `playerStore.play(book)`
- If this book is the currently playing book, show a pause button instead

---

## Critical Files

| File | Change |
|------|--------|
| `backend/internal/db/schema.sql` | Add `file_path`, `playback_position_ms` columns |
| `backend/internal/jobs/download.go` | Save `file_path` on download completion |
| `backend/internal/api/library.go` | Add `StreamBook`, `GetBookChapters` handlers; extend PATCH |
| `backend/internal/api/router.go` | Register 2 new routes |
| `frontend/src/api/client.ts` | Add `getChapters`, update PATCH payload type |
| `frontend/src/stores/player.ts` | **New** — player Pinia store |
| `frontend/src/components/shared/PlayerBar.vue` | **New** — bottom bar UI |
| `frontend/src/App.vue` | Mount PlayerBar, add bottom padding |
| `frontend/src/components/library/BookDetailPanel.vue` | Add Play button |

---

## Verification

1. Download a liberated book, click Play in the detail panel → PlayerBar appears at the bottom
2. Audio plays; scrubber advances; chapter name updates as playback progresses
3. Click scrubber to seek → audio jumps to that position
4. Click `<<30` / `30>>` → skips correctly
5. Change playback speed → playback rate changes
6. Reload the page, click Play on the same book → audio resumes from saved position
7. m4b without chapters (or mp3) → chapters endpoint returns `[]`, no chapter nav shown
8. Run `go build ./...` to confirm backend compiles
9. Run `npm run type-check` in `frontend/` to confirm TypeScript is clean
