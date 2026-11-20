# Libera

A self-hosted web app for your Audible library: scan your books, download and
decrypt them to M4B or MP3 with Audible's real chapter titles embedded, and
keep them organised in one folder per book. Inspired by
[Libation](https://github.com/rmcrackan/Libation).

One container: a FastAPI backend that also serves the Vue frontend.

## Run it

```sh
cp .env.example .env      # set AUDIOBOOKS_DIR, PUID/PGID, PORT
docker compose up -d --build
```

Open http://localhost:8888, add your Audible account under **Accounts**, then
scan your library.

| Setting (`.env`) | Default | What it does |
|---|---|---|
| `PORT` | `8888` | Host port for the app |
| `AUDIOBOOKS_DIR` | `./data/audiobooks` | Where downloaded books go |
| `DATA_DIR` | `./data` | Database (`db/`) and Audible login tokens (`accounts/`) |
| `PUID` / `PGID` | `0` (root) | Owner of the files the app writes; match your media folder |
| `APP_URL` | `http://localhost:8888` | The app's public URL, shown in Settings |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | Send OpenTelemetry traces to this OTLP gRPC endpoint |

File naming, the per-book folder, default format and the number of parallel
downloads are set in the app's **Settings** page.

Host-specific Docker tweaks (an extra network, a tracing endpoint) go in a
`docker-compose.override.yml`, which is gitignored.

## Develop

```sh
# backend on :8080 (needs Python 3.12, ffmpeg, and SQLite >= 3.43)
cd server && pip install -r requirements-dev.txt
DATABASE_PATH=../data/db/libera.db ACCOUNTS_DIR=../data/accounts \
  OUTPUT_DIR=../data/audiobooks uvicorn app.main:app --reload --port 8080

# frontend on :5173, proxying /api to :8080
cd frontend && npm install && npm run dev
```

Tests run in the same base image as the app:

```sh
docker build --target test -t libera-test . && docker run --rm libera-test
```

Layout: `server/app` (API, Audible client, download jobs), `server/tests`,
`frontend/` (Vue 3 + Vite). Design notes are in `docs/plans/`.
