package api

import (
	"encoding/json"
	"net/http"
)

func (h *handlers) getSettings(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, map[string]any{
		"app_url":          h.cfg.AppURL,
		"output_dir":       h.cfg.OutputDir,
		"download_workers": h.cfg.DownloadWorkers,
	})
}

func (h *handlers) updateSettings(w http.ResponseWriter, r *http.Request) {
	var patch struct {
		OutputDir       *string `json:"output_dir"`
		DownloadWorkers *int    `json:"download_workers"`
	}
	if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}
	// TODO: persist settings overrides to DB or config file
	w.WriteHeader(http.StatusNoContent)
}
