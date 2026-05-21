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
	outputDir, defaultFormat, filenameTemplate, _ := h.cfg.Read()
	if req.Format == "" {
		req.Format = defaultFormat
	}

	type bookMeta struct {
		audibleAccountID string
		title            string
		language         string
		lengthMinutes    int
		dateAdded        string
	}
	var meta bookMeta
	if err := h.db.QueryRowContext(r.Context(),
		`SELECT a.audible_account_id, b.title,
		        COALESCE(b.language,''), COALESCE(b.length_minutes,0), COALESCE(lb.date_added,'')
		 FROM accounts a
		 JOIN library_books lb ON lb.account_id = a.id
		 JOIN books b ON b.id = lb.book_id
		 WHERE a.id = ? AND b.id = ?`,
		req.AccountID, req.BookID).Scan(
		&meta.audibleAccountID, &meta.title,
		&meta.language, &meta.lengthMinutes, &meta.dateAdded); err != nil {
		httpError(w, err, http.StatusNotFound)
		return
	}

	// Fetch authors, narrators, and series for filename template rendering.
	var authors, narrators []string
	cRows, _ := h.db.QueryContext(r.Context(),
		`SELECT c.name, bc.role FROM contributors c
		 JOIN book_contributors bc ON bc.contributor_id = c.id
		 WHERE bc.book_id = ? ORDER BY bc.role, bc.sort_order`, req.BookID)
	if cRows != nil {
		for cRows.Next() {
			var name, role string
			cRows.Scan(&name, &role)
			if role == "author" {
				authors = append(authors, name)
			} else if role == "narrator" {
				narrators = append(narrators, name)
			}
		}
		cRows.Close()
	}
	var seriesName, seriesIndex string
	h.db.QueryRowContext(r.Context(),
		`SELECT s.name, COALESCE(sb.book_index,'') FROM series s
		 JOIN series_books sb ON sb.series_id = s.id
		 WHERE sb.book_id = ? LIMIT 1`, req.BookID).Scan(&seriesName, &seriesIndex)

	year := ""
	if len(meta.dateAdded) >= 4 {
		year = meta.dateAdded[:4]
	}

	durationH := ""
	if meta.lengthMinutes > 0 {
		durationH = fmt.Sprintf("%d", meta.lengthMinutes/60)
	}

	job := jobs.DownloadJob{
		ID:               fmt.Sprintf("dl-%d-%d", req.BookID, time.Now().UnixMilli()),
		BookID:           req.BookID,
		AudibleID:        req.AudibleID,
		AccountID:        req.AccountID,
		AudibleAccountID: meta.audibleAccountID,
		Title:            meta.title,
		Authors:          joinStrings(authors),
		Narrators:        joinStrings(narrators),
		SeriesName:       seriesName,
		SeriesIndex:      seriesIndex,
		Language:         meta.language,
		LengthMinutes:    meta.lengthMinutes,
		DateAdded:        meta.dateAdded,
		Format:           req.Format,
		OutputDir:        outputDir,
		FilenameTemplate: filenameTemplate,
		DurationH:        durationH,
		Year:             year,
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
