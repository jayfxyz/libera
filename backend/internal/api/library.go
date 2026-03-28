package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/web-libation/backend/internal/audible"
)

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
	_ = id
	// TODO: full book detail with contributors, series, categories
	writeJSON(w, map[string]any{})
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
