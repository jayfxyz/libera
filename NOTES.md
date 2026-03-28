Instructions for Agents:
    Questions: These are questions that need to be answered before the project can move forward. They may require research, discussion, or decision-making. If answers aren't long, provide the answer right below the question. Otherwise, create a new section in the notes for the answer and link the question to that section.
    Tasks: decide if you can spawn agents to tackle these tasks in parallel or if some tasks depend on the completion of others.

## Questions:

* A new name for the project.
    **Suggestion: "Cellar"** — evokes a wine cellar (staying in the Libation family) and a personal collection you curate and store. Clean, memorable, and works well as a domain/app name.

* What does the download pipeline look like? How should the UX look like?
    See [Download Pipeline UX](#download-pipeline-ux).

    What if the user moves the file after liberation? What should the app show?
    The app has no way to know the file was moved (no filesystem watcher). Best approach: keep `download_status` as `downloaded` but add a "Verify" or "Re-download" button in the book detail panel. Optionally, on re-download attempt, check if the file still exists at `last_format` path and surface a warning if not.

* /api/library?page=1
    I don't like the "liberation" concept in response: `liberation_status: "not_liberated"`
    **Suggestion:** Rename to `download_status` with cleaner values:
    - `none` (was `not_liberated`)
    - `downloaded` (was `liberated`)
    - `error` (unchanged)
    - `partial` (was `partial_download`)
    This removes the Libation-specific jargon and makes the API more intuitive.

* What features am I missing from the original /Libation project?
    See [Missing Libation Features](#missing-libation-features).
* Can we change the Account registration UX to: iframe instead of new tab? So that we can programatically get the auth token and avoid asking users to copy/paste it.
    **Short answer: No — Amazon blocks iframes.** Amazon sets `X-Frame-Options: SAMEORIGIN` and `Content-Security-Policy: frame-ancestors 'self'` on their login pages, so an `<iframe>` will be blocked by all modern browsers.
    **Alternatives to the copy-paste flow:**
    1. **Redirect to a local callback URL** (best UX): Instead of the user copying the maplanding URL, configure the OAuth `redirect_uri` to point at a local endpoint (e.g., `http://localhost:PORT/auth/callback`). The browser is redirected there automatically after login, and the backend captures the code. This requires controlling the OAuth redirect URI, which may need changes to the audible-svc registration parameters.
    2. **Browser extension** (niche): A companion extension could intercept the maplanding redirect and post the URL to the app automatically, eliminating the copy-paste step. Too complex for most users.
    3. **Keep copy-paste but improve UX**: Show a clearer animation/instruction, auto-detect when a valid URL is pasted (the URL format is predictable), and auto-submit.
    **Recommended**: Investigate whether audible-svc's `/auth/register` can accept a custom `redirect_uri` pointing to the local server. If so, the flow becomes: open tab → user logs in → Amazon redirects to `localhost/api/accounts/auth/callback?code=...` → backend completes auth automatically, no copy-paste needed.

## Tasks:
* ~~The Library page should visually indicate the liberation status of each item (e.g., with icons or color coding).~~
    Already implemented — BookCard shows colored badges (green ✓, red ✗, yellow ~) for liberated/error/partial_download. "Not liberated" shows no badge (intentional — no badge = not downloaded).

* The Library page should have filters (pills) for:
    * "All" (default)
    * "Liberated"
    * "Not Liberated"
    * "In Progress"

* Accounts: Abiility  to edit an Account name
* Accounts: Include country emoji flag in the UI
* Accounts: Include a "last scanned at" timestamp in the UI
* Library page: when book is clicked, show slide-out with details about the book.

## Needs further thinking:


---

## Download Pipeline UX

**Current flow:**
1. User clicks "Download" on a book card (appears on hover)
2. Job is enqueued → status: `queued`
3. Backend downloads the `.aax` from Audible → status: `downloading` (with % progress)
4. ffmpeg decrypts `.aax` → `.m4b` → status: `decrypting`
5. Done → status: `done`, file path shown in Downloads view

**UX recommendations:**
- The current hover-only download button is fine for the grid view.
- Show real-time progress in the Downloads page (already works via WebSocket).
- In the book detail slide-out, show download status prominently with a progress bar if actively downloading.
- On completion, show the output file path and a "Re-download" option.
- The "In Progress" filter pill should match books whose `download_status` is `partial` OR currently in the active download queue.

**If the user moves/deletes the file after download:**
- The app has no filesystem watcher, so it can't detect this automatically.
- Keep `download_status: downloaded` in the DB.
- In the book detail slide-out, show the expected file path and a note that it may have been moved.
- Offer a "Re-download" button regardless of download status.


---

## Missing Libation Features

Compared to the original [Libation](https://github.com/rmcrackan/Libation) desktop app, these features are absent or not yet implemented:

| Feature | Notes |
|---|---|
| **PDF liberation** | Libation downloads supplemental PDFs that come with some audiobooks |
| **Export library** | Libation exports to Excel (XLSX), CSV, and JSON — useful for backup/analysis |
| **Custom file naming templates** | Libation lets you define the output path/filename pattern (e.g., `{Author}/{Series}/{Title}`) |
| **Chapter splitting** | Libation can split one big `.m4b` into per-chapter files |
| **Quick Filters / hotkeys** | Libation has saved filter presets with keyboard shortcuts |
| **CLI (`libationcli`)** | Libation has a full CLI for scripting, batch downloads, CI use |
| **Abridged/Spatial/Plus tags** | Libation surfaces these prominently; web-libation tracks them in the DB but doesn't show them in the UI |
| **Read/Unread tracking** | `is_finished` exists in the DB but isn't surfaced in the UI |
| **User ratings** | `user_rating` exists in the DB but isn't surfaced in the UI |
| **Audible rating display** | The book detail view should show the Audible community rating |

Most impactful to add next (in order): export library → custom naming templates → chapter splitting.
