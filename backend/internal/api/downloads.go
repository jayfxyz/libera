package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/web-libation/backend/internal/jobs"
)

func (h *handlers) enqueueDownload(w http.ResponseWriter, r *http.Request) {
	var req struct {
		BookID    int64  `json:"book_id"`
		AudibleID string `json:"audible_id"`
		AccountID int64  `json:"account_id"`
		Format    string `json:"format"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}
	outputDir, defaultFormat, _ := h.cfg.Read()
	if req.Format == "" {
		req.Format = defaultFormat
	}

	var audibleAccountID, title string
	if err := h.db.QueryRowContext(r.Context(),
		`SELECT a.audible_account_id, b.title
		 FROM accounts a
		 JOIN library_books lb ON lb.account_id = a.id
		 JOIN books b ON b.id = lb.book_id
		 WHERE a.id = ? AND b.id = ?`,
		req.AccountID, req.BookID).Scan(&audibleAccountID, &title); err != nil {
		httpError(w, err, http.StatusNotFound)
		return
	}

	job := jobs.DownloadJob{
		ID:               fmt.Sprintf("dl-%d-%d", req.BookID, time.Now().UnixMilli()),
		BookID:           req.BookID,
		AudibleID:        req.AudibleID,
		AccountID:        req.AccountID,
		AudibleAccountID: audibleAccountID,
		Title:            title,
		Format:           req.Format,
		OutputDir:        outputDir,
	}
	h.queue.Enqueue(r.Context(), job)

	w.WriteHeader(http.StatusAccepted)
	writeJSON(w, map[string]string{"job_id": job.ID})
}

func (h *handlers) listDownloads(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, h.queue.ListJobs())
}

func (h *handlers) cancelDownload(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !h.queue.Cancel(id) {
		http.NotFound(w, r)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
