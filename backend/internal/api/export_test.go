package api

import (
	"encoding/csv"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/web-libation/backend/internal/db"
)

func TestExportLibrary_JSON(t *testing.T) {
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatal(err)
	}
	defer database.Close()
	if err := db.Migrate(database); err != nil {
		t.Fatal(err)
	}

	// Seed a book via importLibrary
	if _, err := importLibrary(t.Context(), database, 1, makeBooks("EX01")); err != nil {
		t.Fatal(err)
	}

	h := &handlers{db: database}
	req := httptest.NewRequest(http.MethodGet, "/library/export?format=json", nil)
	w := httptest.NewRecorder()
	h.exportLibrary(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
	if ct := w.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Errorf("unexpected Content-Type: %q", ct)
	}

	var rows []map[string]any
	if err := json.NewDecoder(w.Body).Decode(&rows); err != nil {
		t.Fatalf("decode JSON: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("want 1 row, got %d", len(rows))
	}
	if rows[0]["audible_id"] != "EX01" {
		t.Errorf("unexpected audible_id: %v", rows[0]["audible_id"])
	}
}

func TestExportLibrary_CSV(t *testing.T) {
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatal(err)
	}
	defer database.Close()
	if err := db.Migrate(database); err != nil {
		t.Fatal(err)
	}

	if _, err := importLibrary(t.Context(), database, 1, makeBooks("EX01", "EX02")); err != nil {
		t.Fatal(err)
	}

	h := &handlers{db: database}
	req := httptest.NewRequest(http.MethodGet, "/library/export?format=csv", nil)
	w := httptest.NewRecorder()
	h.exportLibrary(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d: %s", w.Code, w.Body.String())
	}
	if ct := w.Header().Get("Content-Type"); !strings.HasPrefix(ct, "text/csv") {
		t.Errorf("unexpected Content-Type: %q", ct)
	}

	records, err := csv.NewReader(w.Body).ReadAll()
	if err != nil {
		t.Fatalf("parse CSV: %v", err)
	}
	// header + 2 data rows
	if len(records) != 3 {
		t.Fatalf("want 3 CSV rows (header+2), got %d", len(records))
	}
	// Header row must include audible_id
	found := false
	for _, h := range records[0] {
		if h == "audible_id" {
			found = true
		}
	}
	if !found {
		t.Errorf("CSV header missing 'audible_id': %v", records[0])
	}
}

func TestExportLibrary_InvalidFormat(t *testing.T) {
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatal(err)
	}
	defer database.Close()
	db.Migrate(database)

	h := &handlers{db: database}
	req := httptest.NewRequest(http.MethodGet, "/library/export?format=xml", nil)
	w := httptest.NewRecorder()
	h.exportLibrary(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400 for invalid format, got %d", w.Code)
	}
}
