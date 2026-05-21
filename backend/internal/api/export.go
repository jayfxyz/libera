package api

import (
	"encoding/csv"
	"encoding/json"
	"net/http"
	"strconv"
)

type exportRow struct {
	AudibleID        string  `json:"audible_id"`
	Title            string  `json:"title"`
	Authors          string  `json:"authors"`
	Narrators        string  `json:"narrators"`
	Series           string  `json:"series"`
	LengthMinutes    int     `json:"length_minutes"`
	Publisher        string  `json:"publisher"`
	Language         string  `json:"language"`
	AudibleRating    float32 `json:"audible_rating"`
	LiberationStatus string  `json:"liberation_status"`
	IsFinished       bool    `json:"is_finished"`
	Tags             string  `json:"tags"`
	UserRating       *int    `json:"user_rating"`
	DateAdded        string  `json:"date_added"`
}

func (h *handlers) exportLibrary(w http.ResponseWriter, r *http.Request) {
	format := r.URL.Query().Get("format")
	if format == "" {
		format = "json"
	}
	if format != "json" && format != "csv" {
		http.Error(w, "format must be 'json' or 'csv'", http.StatusBadRequest)
		return
	}

	rows, err := h.db.QueryContext(r.Context(), `
		SELECT b.audible_id, b.title,
		       COALESCE(b.length_minutes, 0), COALESCE(b.publisher,''),
		       COALESCE(b.language,''), COALESCE(b.audible_rating,0),
		       lb.liberation_status, lb.is_finished, lb.tags,
		       lb.user_rating, lb.date_added
		FROM books b
		JOIN library_books lb ON lb.book_id = b.id
		WHERE lb.is_deleted = 0
		ORDER BY b.title`)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	// Gather contributor and series data per book for denormalized export
	type rawRow struct {
		exportRow
		bookID int64
	}
	var data []rawRow
	for rows.Next() {
		var rr rawRow
		var userRatingNull *int64
		if err := rows.Scan(
			&rr.AudibleID, &rr.Title,
			&rr.LengthMinutes, &rr.Publisher,
			&rr.Language, &rr.AudibleRating,
			&rr.LiberationStatus, &rr.IsFinished, &rr.Tags,
			&userRatingNull, &rr.DateAdded,
		); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		if userRatingNull != nil {
			v := int(*userRatingNull)
			rr.UserRating = &v
		}
		data = append(data, rr)
	}
	if err := rows.Err(); err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}

	// Enrich with authors/narrators/series from linked tables
	for i := range data {
		var bookID int64
		h.db.QueryRowContext(r.Context(),
			`SELECT id FROM books WHERE audible_id = ?`, data[i].AudibleID).Scan(&bookID)

		// Contributors
		cRows, _ := h.db.QueryContext(r.Context(),
			`SELECT c.name, bc.role FROM contributors c
			 JOIN book_contributors bc ON bc.contributor_id = c.id
			 WHERE bc.book_id = ?`, bookID)
		var authors, narrators []string
		if cRows != nil {
			for cRows.Next() {
				var name, role string
				cRows.Scan(&name, &role)
				if role == "author" {
					authors = append(authors, name)
				} else {
					narrators = append(narrators, name)
				}
			}
			cRows.Close()
		}
		data[i].Authors = joinStrings(authors)
		data[i].Narrators = joinStrings(narrators)

		// Series
		sRows, _ := h.db.QueryContext(r.Context(),
			`SELECT s.name FROM series s
			 JOIN series_books sb ON sb.series_id = s.id
			 WHERE sb.book_id = ?`, bookID)
		var seriesList []string
		if sRows != nil {
			for sRows.Next() {
				var name string
				sRows.Scan(&name)
				seriesList = append(seriesList, name)
			}
			sRows.Close()
		}
		data[i].Series = joinStrings(seriesList)
	}

	exportRows := make([]exportRow, len(data))
	for i, rr := range data {
		exportRows[i] = rr.exportRow
	}

	if format == "json" {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Content-Disposition", "attachment; filename=library.json")
		json.NewEncoder(w).Encode(exportRows)
		return
	}

	// CSV
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", "attachment; filename=library.csv")
	cw := csv.NewWriter(w)
	cw.Write([]string{
		"audible_id", "title", "authors", "narrators", "series",
		"length_minutes", "publisher", "language", "audible_rating",
		"liberation_status", "is_finished", "tags", "user_rating", "date_added",
	})
	for _, r := range exportRows {
		rating := ""
		if r.UserRating != nil {
			rating = strconv.Itoa(*r.UserRating)
		}
		cw.Write([]string{
			r.AudibleID, r.Title, r.Authors, r.Narrators, r.Series,
			strconv.Itoa(r.LengthMinutes), r.Publisher, r.Language,
			strconv.FormatFloat(float64(r.AudibleRating), 'f', 2, 32),
			r.LiberationStatus, strconv.FormatBool(r.IsFinished), r.Tags, rating, r.DateAdded,
		})
	}
	cw.Flush()
}

func joinStrings(ss []string) string {
	out := ""
	for i, s := range ss {
		if i > 0 {
			out += ", "
		}
		out += s
	}
	return out
}
