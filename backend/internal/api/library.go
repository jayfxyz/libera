package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/web-libation/backend/internal/audible"
)

var unsafeChars = regexp.MustCompile(`[<>:"/\\|?*\x00-\x1f]`)

// TODO: find better solution for the app to match library items to files on disk.
func sanitizeFilename(s string) string {
	s = unsafeChars.ReplaceAllString(s, "_")
	s = strings.TrimSpace(s)
	if len(s) > 200 {
		s = s[:200]
	}
	if s == "" {
		s = "audiobook"
	}
	return s
}

type bookRow struct {
	ID               int64  `json:"id"`
	AudibleID        string `json:"audible_id"`
	Title            string `json:"title"`
	CoverURL         string `json:"cover_url"`
	LiberationStatus string `json:"liberation_status"`
	IsFinished       bool   `json:"is_finished"`
	Tags             string `json:"tags"`
	AccountID        int64  `json:"account_id"`
}

func (h *handlers) listLibrary(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	search := q.Get("q")
	page := 1
	pageSize := 50

	if p := q.Get("page"); p != "" {
		if n, err := strconv.Atoi(p); err == nil && n > 0 {
			page = n
		}
	}

	offset := (page - 1) * pageSize

	var (
		rows *sql.Rows
		err  error
	)

	if search != "" {
		rows, err = h.db.QueryContext(r.Context(), `
			SELECT b.id, b.audible_id, b.title, b.cover_url, lb.liberation_status, lb.is_finished, lb.tags, lb.account_id
			FROM books b
			JOIN library_books lb ON lb.book_id = b.id
			JOIN books_fts f ON f.rowid = b.id
			WHERE books_fts MATCH ?
			ORDER BY rank
			LIMIT ? OFFSET ?`, search, pageSize, offset)
	} else {
		rows, err = h.db.QueryContext(r.Context(), `
			SELECT b.id, b.audible_id, b.title, b.cover_url, lb.liberation_status, lb.is_finished, lb.tags, lb.account_id
			FROM books b
			JOIN library_books lb ON lb.book_id = b.id
			WHERE lb.is_deleted = 0
			ORDER BY b.title
			LIMIT ? OFFSET ?`, pageSize, offset)
	}
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	books := []bookRow{}
	for rows.Next() {
		var b bookRow
		if err := rows.Scan(&b.ID, &b.AudibleID, &b.Title, &b.CoverURL, &b.LiberationStatus, &b.IsFinished, &b.Tags, &b.AccountID); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		books = append(books, b)
	}

	writeJSON(w, books)
}

func (h *handlers) getBook(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	if err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}

	type bookDetail struct {
		ID               int64    `json:"id"`
		AudibleID        string   `json:"audible_id"`
		Title            string   `json:"title"`
		Subtitle         string   `json:"subtitle"`
		Description      string   `json:"description"`
		CoverURL         string   `json:"cover_url"`
		LengthMinutes    int      `json:"length_minutes"`
		Publisher        string   `json:"publisher"`
		Language         string   `json:"language"`
		AudibleRating    float32  `json:"audible_rating"`
		LiberationStatus string   `json:"liberation_status"`
		IsFinished       bool     `json:"is_finished"`
		Tags             string   `json:"tags"`
		UserRating       *float32 `json:"user_rating"`
		AccountID        int64    `json:"account_id"`
		Authors          []string `json:"authors"`
		Narrators        []string `json:"narrators"`
		Series           []struct {
			Name  string `json:"name"`
			Index string `json:"index"`
		} `json:"series"`
	}

	var d bookDetail
	var userRating sql.NullFloat64
	err = h.db.QueryRowContext(r.Context(), `
		SELECT b.id, b.audible_id, b.title, COALESCE(b.subtitle,''), COALESCE(b.description,''),
		       COALESCE(b.cover_url,''), b.length_minutes, COALESCE(b.publisher,''),
		       COALESCE(b.language,''), COALESCE(b.audible_rating,0),
		       lb.liberation_status, lb.is_finished, lb.tags, lb.user_rating, lb.account_id
		FROM books b
		JOIN library_books lb ON lb.book_id = b.id
		WHERE b.id = ?`, id).Scan(
		&d.ID, &d.AudibleID, &d.Title, &d.Subtitle, &d.Description,
		&d.CoverURL, &d.LengthMinutes, &d.Publisher, &d.Language, &d.AudibleRating,
		&d.LiberationStatus, &d.IsFinished, &d.Tags, &userRating, &d.AccountID)
	if err == sql.ErrNoRows {
		http.NotFound(w, r)
		return
	}
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}
	if userRating.Valid {
		v := float32(userRating.Float64)
		d.UserRating = &v
	}

	// Contributors
	contribRows, err := h.db.QueryContext(r.Context(), `
		SELECT c.name, bc.role FROM contributors c
		JOIN book_contributors bc ON bc.contributor_id = c.id
		WHERE bc.book_id = ? ORDER BY bc.role, bc.sort_order`, id)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}
	defer contribRows.Close()
	d.Authors = []string{}
	d.Narrators = []string{}
	for contribRows.Next() {
		var name, role string
		if err := contribRows.Scan(&name, &role); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		if role == "author" {
			d.Authors = append(d.Authors, name)
		} else if role == "narrator" {
			d.Narrators = append(d.Narrators, name)
		}
	}

	// Series
	seriesRows, err := h.db.QueryContext(r.Context(), `
		SELECT s.name, COALESCE(sb.book_index,'') FROM series s
		JOIN series_books sb ON sb.series_id = s.id
		WHERE sb.book_id = ?`, id)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}
	defer seriesRows.Close()
	d.Series = []struct {
		Name  string `json:"name"`
		Index string `json:"index"`
	}{}
	for seriesRows.Next() {
		var s struct {
			Name  string `json:"name"`
			Index string `json:"index"`
		}
		if err := seriesRows.Scan(&s.Name, &s.Index); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		d.Series = append(d.Series, s)
	}

	writeJSON(w, d)
}

// importLibrary upserts books from an Audible library scan into the DB.
// Returns the number of books processed.
func importLibrary(ctx context.Context, db *sql.DB, accountID int64, books []audible.BookDTO) (int, error) {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()

	for _, b := range books {
		// Upsert book
		res, err := tx.ExecContext(ctx, `
			INSERT INTO books (audible_id, title, subtitle, description, length_minutes, locale, cover_url, publisher, audible_rating)
			VALUES (?, ?, ?, ?, ?, '', ?, ?, ?)
			ON CONFLICT(audible_id) DO UPDATE SET
				title = excluded.title,
				cover_url = excluded.cover_url,
				audible_rating = excluded.audible_rating`,
			b.AudibleID, b.Title, b.Subtitle, b.Description,
			b.LengthMinutes, b.CoverURL, b.Publisher, b.AudibleRating)
		if err != nil {
			return 0, err
		}

		bookID, err := res.LastInsertId()
		if err != nil {
			// ON CONFLICT path — fetch existing id
			if err2 := tx.QueryRowContext(ctx,
				`SELECT id FROM books WHERE audible_id = ?`, b.AudibleID).Scan(&bookID); err2 != nil {
				return 0, err2
			}
		}

		// Upsert library_books link
		dateAdded := b.DateAdded
		if dateAdded == "" {
			dateAdded = "1970-01-01"
		}
		isPlus := 0
		if b.IsAudiblePlus {
			isPlus = 1
		}
		_, err = tx.ExecContext(ctx, `
			INSERT INTO library_books (book_id, account_id, date_added, is_audible_plus)
			VALUES (?, ?, ?, ?)
			ON CONFLICT(book_id, account_id) DO UPDATE SET
				date_added = excluded.date_added`,
			bookID, accountID, dateAdded, isPlus)
		if err != nil {
			return 0, err
		}

		// Contributors (authors + narrators)
		for _, name := range b.Authors {
			if err := upsertContributor(ctx, tx, bookID, name, "author"); err != nil {
				return 0, err
			}
		}
		for _, name := range b.Narrators {
			if err := upsertContributor(ctx, tx, bookID, name, "narrator"); err != nil {
				return 0, err
			}
		}

		// Series
		for _, s := range b.Series {
			if s.AudibleID == "" {
				continue
			}
			if _, err := tx.ExecContext(ctx,
				`INSERT INTO series (audible_id, name) VALUES (?, ?)
				 ON CONFLICT(audible_id) DO UPDATE SET name = excluded.name`,
				s.AudibleID, s.Title); err != nil {
				return 0, err
			}
			var seriesID int64
			if err := tx.QueryRowContext(ctx,
				`SELECT id FROM series WHERE audible_id = ?`, s.AudibleID).Scan(&seriesID); err != nil {
				return 0, err
			}
			if _, err := tx.ExecContext(ctx,
				`INSERT OR IGNORE INTO series_books (series_id, book_id, book_index) VALUES (?, ?, ?)`,
				seriesID, bookID, s.Sequence); err != nil {
				return 0, err
			}
		}

		// FTS update — virtual tables don't support upsert, use DELETE + INSERT
		authorStr := strings.Join(b.Authors, ", ")
		narratorStr := strings.Join(b.Narrators, ", ")
		seriesTitles := make([]string, 0, len(b.Series))
		for _, s := range b.Series {
			seriesTitles = append(seriesTitles, s.Title)
		}
		if _, err := tx.ExecContext(ctx, `DELETE FROM books_fts WHERE rowid = ?`, bookID); err != nil {
			return 0, err
		}
		if _, err := tx.ExecContext(ctx,
			`INSERT INTO books_fts (rowid, title, subtitle, description, authors, narrators, series_name, tags)
			 VALUES (?, ?, ?, ?, ?, ?, ?, '')`,
			bookID, b.Title, b.Subtitle, b.Description,
			authorStr, narratorStr, strings.Join(seriesTitles, ", ")); err != nil {
			return 0, err
		}
	}

	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return len(books), nil
}

func upsertContributor(ctx context.Context, tx *sql.Tx, bookID int64, name, role string) error {
	if _, err := tx.ExecContext(ctx,
		`INSERT INTO contributors (name) VALUES (?) ON CONFLICT(name) DO NOTHING`, name); err != nil {
		return err
	}
	var cID int64
	if err := tx.QueryRowContext(ctx,
		`SELECT id FROM contributors WHERE name = ?`, name).Scan(&cID); err != nil {
		return err
	}
	_, err := tx.ExecContext(ctx,
		`INSERT OR IGNORE INTO book_contributors (book_id, contributor_id, role) VALUES (?, ?, ?)`,
		bookID, cID, role)
	return err
}

func (h *handlers) rescanFiles(w http.ResponseWriter, r *http.Request) {
	entries, err := os.ReadDir(h.cfg.OutputDir)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}

	// Build a map of basename (no ext) → format for audio files on disk
	onDisk := map[string]string{}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(e.Name()))
		if ext != ".m4b" && ext != ".mp3" {
			continue
		}
		base := strings.TrimSuffix(e.Name(), filepath.Ext(e.Name()))
		onDisk[base] = strings.TrimPrefix(ext, ".")
	}

	if len(onDisk) == 0 {
		writeJSON(w, map[string]int{"matched": 0})
		return
	}

	// Fetch all non-liberated books and collect matches (must close rows before UPDATE — single connection)
	rows, err := h.db.QueryContext(r.Context(),
		`SELECT b.id, b.title FROM books b
		 JOIN library_books lb ON lb.book_id = b.id
		 WHERE lb.liberation_status != 'liberated'`)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}

	type match struct {
		id     int64
		format string
	}
	var matches []match
	for rows.Next() {
		var id int64
		var title string
		if err := rows.Scan(&id, &title); err != nil {
			continue
		}
		if format, found := onDisk[sanitizeFilename(title)]; found {
			matches = append(matches, match{id, format})
		}
	}
	rows.Close()

	for _, m := range matches {
		h.db.ExecContext(r.Context(),
			`UPDATE library_books SET liberation_status = 'liberated', last_downloaded = CURRENT_TIMESTAMP, last_format = ? WHERE book_id = ?`,
			m.format, m.id)
	}

	writeJSON(w, map[string]int{"matched": len(matches)})
}

func (h *handlers) updateBook(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	if err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}

	var patch struct {
		Tags       *string  `json:"tags"`
		UserRating *float32 `json:"user_rating"`
		IsFinished *bool    `json:"is_finished"`
	}
	if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}

	if patch.Tags != nil {
		h.db.ExecContext(r.Context(), `UPDATE library_books SET tags = ? WHERE book_id = ?`, *patch.Tags, id)
	}
	if patch.UserRating != nil {
		h.db.ExecContext(r.Context(), `UPDATE library_books SET user_rating = ? WHERE book_id = ?`, *patch.UserRating, id)
	}
	if patch.IsFinished != nil {
		h.db.ExecContext(r.Context(), `UPDATE library_books SET is_finished = ? WHERE book_id = ?`, *patch.IsFinished, id)
	}

	w.WriteHeader(http.StatusNoContent)
}
