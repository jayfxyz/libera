package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/web-libation/backend/internal/audible"
	"github.com/web-libation/backend/internal/db"
)

func sortTestHandlers(t *testing.T) *handlers {
	t.Helper()
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { database.Close() })
	if err := db.Migrate(database); err != nil {
		t.Fatal(err)
	}

	books := []audible.BookDTO{
		{AudibleID: "A", Title: "beta", Authors: []string{"Zed"}, DateAdded: "2024-03-01",
			DatePublished: "2001-05-01", LengthMinutes: 300, AudibleRating: 4.1,
			Series: []audible.SeriesDTO{{AudibleID: "S1", Title: "Saga", Sequence: "10"}}},
		{AudibleID: "B", Title: "Alpha", Authors: []string{"Amy"}, DateAdded: "2024-01-01",
			DatePublished: "2020-01-01", LengthMinutes: 900, AudibleRating: 4.8,
			Series: []audible.SeriesDTO{{AudibleID: "S1", Title: "Saga", Sequence: "2"}}},
		// No release date, rating or series: always sorts last for those.
		{AudibleID: "C", Title: "Gamma", Authors: []string{"Mo"}, DateAdded: "2024-02-01",
			LengthMinutes: 60},
	}
	if _, err := importLibrary(context.Background(), database, 1, books); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec(`UPDATE library_books SET last_downloaded = '2026-01-01'
		WHERE book_id = (SELECT id FROM books WHERE audible_id = 'C')`); err != nil {
		t.Fatal(err)
	}
	return &handlers{db: database}
}

func listASINs(t *testing.T, h *handlers, query string) ([]string, int) {
	t.Helper()
	w := httptest.NewRecorder()
	h.listLibrary(w, httptest.NewRequest(http.MethodGet, "/library?"+query, nil))
	if w.Code != http.StatusOK {
		return nil, w.Code
	}
	var rows []bookRow
	if err := json.Unmarshal(w.Body.Bytes(), &rows); err != nil {
		t.Fatal(err)
	}
	out := make([]string, len(rows))
	for i, r := range rows {
		out[i] = r.AudibleID
	}
	return out, w.Code
}

func TestListLibrary_Sort(t *testing.T) {
	h := sortTestHandlers(t)
	cases := []struct {
		query string
		want  []string
	}{
		{"", []string{"B", "A", "C"}}, // title, case-insensitive
		{"sort=title&order=desc", []string{"C", "A", "B"}},
		{"sort=author", []string{"B", "C", "A"}}, // Amy, Mo, Zed
		{"sort=added", []string{"A", "C", "B"}},  // newest first
		{"sort=added&order=asc", []string{"B", "C", "A"}},
		{"sort=released", []string{"B", "A", "C"}},           // newest first, unknown last
		{"sort=released&order=asc", []string{"A", "B", "C"}}, // unknown still last
		{"sort=length", []string{"B", "A", "C"}},             // longest first
		{"sort=series", []string{"B", "A", "C"}},             // book 2 before book 10, no series last
		{"sort=rating", []string{"B", "A", "C"}},             // unrated last
		{"sort=downloaded", []string{"C", "B", "A"}},         // never downloaded last, then by title
	}
	for _, c := range cases {
		got, code := listASINs(t, h, c.query)
		if code != http.StatusOK {
			t.Errorf("%q: status %d", c.query, code)
			continue
		}
		if !reflect.DeepEqual(got, c.want) {
			t.Errorf("%q: got %v, want %v", c.query, got, c.want)
		}
	}
}

func TestListLibrary_SortRejectsUnknown(t *testing.T) {
	h := sortTestHandlers(t)
	for _, q := range []string{"sort=b.id%3BDROP%20TABLE%20books", "sort=title&order=sideways"} {
		if _, code := listASINs(t, h, q); code != http.StatusBadRequest {
			t.Errorf("%q: want 400, got %d", q, code)
		}
	}
}

func TestImportLibrary_SavesReleaseDateAndLanguage(t *testing.T) {
	h := sortTestHandlers(t)
	var published, language string
	if err := h.db.QueryRow(`SELECT COALESCE(date_published,''), COALESCE(language,'')
		FROM books WHERE audible_id = 'A'`).Scan(&published, &language); err != nil {
		t.Fatal(err)
	}
	if published != "2001-05-01" {
		t.Errorf("date_published = %q", published)
	}

	// A rescan without a release date keeps the one already stored.
	if _, err := importLibrary(context.Background(), h.db, 1, []audible.BookDTO{
		{AudibleID: "A", Title: "beta", DateAdded: "2024-03-01", Language: "english"},
	}); err != nil {
		t.Fatal(err)
	}
	h.db.QueryRow(`SELECT COALESCE(date_published,''), COALESCE(language,'')
		FROM books WHERE audible_id = 'A'`).Scan(&published, &language)
	if published != "2001-05-01" || language != "english" {
		t.Errorf("after rescan: date_published=%q language=%q", published, language)
	}
}
