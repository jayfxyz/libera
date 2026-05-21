package api

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/web-libation/backend/internal/db"
)

func (h *handlers) getSettings(w http.ResponseWriter, r *http.Request) {
	outputDir, defaultFormat, filenameTemplate, downloadWorkers := h.cfg.Read()
	writeJSON(w, map[string]any{
		"app_url":           h.cfg.AppURL,
		"output_dir":        outputDir,
		"download_workers":  downloadWorkers,
		"default_format":    defaultFormat,
		"filename_template": filenameTemplate,
	})
}

func (h *handlers) updateSettings(w http.ResponseWriter, r *http.Request) {
	var patch struct {
		OutputDir        *string `json:"output_dir"`
		DownloadWorkers  *int    `json:"download_workers"`
		DefaultFormat    *string `json:"default_format"`
		FilenameTemplate *string `json:"filename_template"`
	}
	if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}

	if patch.OutputDir != nil {
		if err := db.SetSetting(h.db, "output_dir", *patch.OutputDir); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		h.cfg.Update("output_dir", *patch.OutputDir)
	}

	if patch.DownloadWorkers != nil {
		val := strconv.Itoa(*patch.DownloadWorkers)
		if err := db.SetSetting(h.db, "download_workers", val); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		h.cfg.Update("download_workers", val)
	}

	if patch.DefaultFormat != nil {
		if *patch.DefaultFormat != "m4b" && *patch.DefaultFormat != "mp3" {
			http.Error(w, "default_format must be 'm4b' or 'mp3'", http.StatusBadRequest)
			return
		}
		if err := db.SetSetting(h.db, "default_format", *patch.DefaultFormat); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		h.cfg.Update("default_format", *patch.DefaultFormat)
	}

	if patch.FilenameTemplate != nil {
		if err := db.SetSetting(h.db, "filename_template", *patch.FilenameTemplate); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		h.cfg.Update("filename_template", *patch.FilenameTemplate)
	}

	w.WriteHeader(http.StatusNoContent)
}
