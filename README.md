# Libera

A self-hosted web app for managing and backing up your Audible library: scan
your books, download and decrypt them to M4B or MP3 with Audible's real chapter
titles and cover art embedded, and keep them organized for media servers like
Audiobookshelf. Inspired by [Libation](https://github.com/rmcrackan/Libation).

One container: a FastAPI backend that also serves the Vue 3 frontend.

## Features

- **Lossless M4B or MP3:** Decrypts AAXC (with AAX fallback) via `ffmpeg` — stream-copied M4B by default, or re-encoded MP3, with per-book overrides.
- **Real chapter titles & cover art:** Embeds Audible's chapter outline and highest-resolution cover into the audio, and writes `cover.jpg`, `.cue`, and `.chapters.json` alongside it.
- **Optional chapter splitting & companion PDFs:** Split audiobooks into per-chapter files on demand and download companion PDFs automatically (or standalone).
- **Audiobookshelf-ready folder layouts:** Pick from flat or nested presets (`Author/Series/1 - Title/`, `Author/Year - Title/`, etc.) in Settings.
- **Multi-account & multi-region:** Connect multiple Audible accounts across regions (`us`, `uk`, `ca`, `de`, `fr`, `au`, `jp`, `in`, `es`, `it`). Books owned by multiple accounts appear as one row.
- **Search, organize & export:** Instant SQLite FTS5 search, status filters, sorting, tags, ratings, finished status, light/dark mode, and CSV/JSON export.
- **Resilient downloads:** Persistent queue with live progress (SSE), automatic backoff when Audible throttles, and retry from the decrypt step without re-downloading.

## Quick start

```sh
cp .env.example .env      # set AUDIOBOOKS_DIR, PUID/PGID, PORT
docker compose up -d --build
```

Open `http://localhost:8888`, add your Audible account under **Accounts**, and
Libera will scan your library.

| Setting (`.env`) | Default | What it does |
|---|---|---|
| `PORT` | `8888` | Host port for the app |
| `AUDIOBOOKS_DIR` | `./data/audiobooks` | Where downloaded books go |
| `DATA_DIR` | `./data` | Database (`db/`) and Audible login tokens (`accounts/`) |
| `PUID` / `PGID` | `0` (root) | Owner of the files the app writes; match your media folder (`id -u` / `id -g`) |
| `APP_URL` | `http://localhost:8888` | The app's public URL, shown in Settings |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Optional: send OpenTelemetry traces to an OTLP gRPC endpoint |

Folder layout presets, default audio format, and parallel download count are
configured in the app's **Settings** page.

Host-specific Docker tweaks (an extra network, reverse proxy labels, a tracing
endpoint) can go in a `docker-compose.override.yml`, which is gitignored.

## Security

Libera has **no built-in authentication** — it is designed to run on a private
network. Do not expose it directly to the public internet without placing it
behind an authenticating reverse proxy (such as Authelia, Authentik, Caddy
basic auth, or Cloudflare Access) or accessing it over a VPN (such as
Tailscale or WireGuard).

## Data & backups

- **`DATA_DIR/db/libera.db`**: Your library metadata, tags, ratings, settings, and download history.
- **`DATA_DIR/accounts/*.json`**: Your Audible device credentials (written with `0600` permissions). Treat these files as secrets and exclude them from public backups.
- **`AUDIOBOOKS_DIR`**: Your decrypted audiobooks, covers, chapter files, and companion PDFs. Temporary work files live in `AUDIOBOOKS_DIR/.incomplete/` while a download is in progress or waiting to be retried.

## Develop

```sh
# backend on :8080 (needs Python 3.12, uv, ffmpeg, and SQLite >= 3.43)
cd server && uv sync
DATABASE_PATH=../data/db/libera.db ACCOUNTS_DIR=../data/accounts \
  OUTPUT_DIR=../data/audiobooks uv run uvicorn app.main:app --reload --port 8080

# frontend on :5173, proxying /api to :8080
cd frontend && npm install && npm run dev
```

Tests run in the same base image as the app:

```sh
docker build --target test -t libera-test . && docker run --rm libera-test
```

Layout: `server/app` (API, Audible client, task queue & download pipeline),
`server/tests`, `frontend/` (Vue 3 + TypeScript + Vite). Design notes live in
`docs/plans/`.

## Credits

Inspired by [Libation](https://github.com/rmcrackan/Libation), and built on
[audible](https://github.com/mkb79/Audible),
[audible-cli](https://github.com/mkb79/audible-cli), and
[FFmpeg](https://ffmpeg.org/).
