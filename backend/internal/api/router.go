package api

import (
	"database/sql"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/web-libation/backend/internal/audible"
	"github.com/web-libation/backend/internal/config"
	"github.com/web-libation/backend/internal/jobs"
)

type handlers struct {
	db      *sql.DB
	audible *audible.Client
	queue   *jobs.Queue
	cfg     *config.Config
}

func NewRouter(db *sql.DB, audible *audible.Client, queue *jobs.Queue, cfg *config.Config) http.Handler {
	h := &handlers{db: db, audible: audible, queue: queue, cfg: cfg}

	r := chi.NewRouter()

	r.Get("/accounts", h.listAccounts)
	r.Post("/accounts", h.createAccount)
	r.Patch("/accounts/{id}", h.updateAccount)
	r.Delete("/accounts/{id}", h.deleteAccount)
	r.Post("/accounts/auth/start", h.authStart)
	r.Post("/accounts/auth/complete", h.authComplete)
	r.Post("/accounts/{id}/scan", h.scanLibrary)

	r.Get("/library", h.listLibrary)
	r.Post("/library/rescan", h.rescanFiles)
	r.Get("/library/{id}", h.getBook)
	r.Patch("/library/{id}", h.updateBook)

	r.Post("/downloads", h.enqueueDownload)
	r.Get("/downloads", h.listDownloads)
	r.Delete("/downloads/{id}", h.cancelDownload)

	r.Get("/settings", h.getSettings)
	r.Patch("/settings", h.updateSettings)

	r.Get("/ws/downloads", h.downloadProgressWS)

	return r
}
