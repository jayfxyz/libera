package api

import (
	"context"
	"database/sql"
	"testing"

	"github.com/web-libation/backend/internal/audible"
	"github.com/web-libation/backend/internal/db"
)

func makeBooks(asins ...string) []audible.BookDTO {
	books := make([]audible.BookDTO, 0, len(asins))
	for _, a := range asins {
		books = append(books, audible.BookDTO{
			AudibleID: a,
			Title:     "Book " + a,
			DateAdded: "2024-01-01",
		})
	}
	return books
}

func countDeleted(t *testing.T, database *sql.DB, accountID int64) int {
	t.Helper()
	var n int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM library_books WHERE account_id = ? AND is_deleted = 1`, accountID,
	).Scan(&n); err != nil {
		t.Fatalf("count deleted: %v", err)
	}
	return n
}

func countActive(t *testing.T, database *sql.DB, accountID int64) int {
	t.Helper()
	var n int
	if err := database.QueryRow(
		`SELECT COUNT(*) FROM library_books WHERE account_id = ? AND is_deleted = 0`, accountID,
	).Scan(&n); err != nil {
		t.Fatalf("count active: %v", err)
	}
	return n
}

func TestImportLibrary_InactiveDetection(t *testing.T) {
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	if err := db.Migrate(database); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	const accountID = int64(1)
	ctx := context.Background()

	// First scan: 3 books
	if _, err := importLibrary(ctx, database, accountID, makeBooks("A1", "A2", "A3")); err != nil {
		t.Fatalf("first import: %v", err)
	}
	if got := countActive(t, database, accountID); got != 3 {
		t.Errorf("after first scan: want 3 active, got %d", got)
	}
	if got := countDeleted(t, database, accountID); got != 0 {
		t.Errorf("after first scan: want 0 deleted, got %d", got)
	}

	// Second scan: A2 was removed from Audible
	if _, err := importLibrary(ctx, database, accountID, makeBooks("A1", "A3")); err != nil {
		t.Fatalf("second import: %v", err)
	}
	if got := countActive(t, database, accountID); got != 2 {
		t.Errorf("after second scan: want 2 active, got %d", got)
	}
	if got := countDeleted(t, database, accountID); got != 1 {
		t.Errorf("after second scan: want 1 deleted, got %d", got)
	}

	// Third scan: A2 comes back (e.g. re-purchased)
	if _, err := importLibrary(ctx, database, accountID, makeBooks("A1", "A2", "A3")); err != nil {
		t.Fatalf("third import: %v", err)
	}
	if got := countActive(t, database, accountID); got != 3 {
		t.Errorf("after third scan: want 3 active (A2 restored), got %d", got)
	}
	if got := countDeleted(t, database, accountID); got != 0 {
		t.Errorf("after third scan: want 0 deleted, got %d", got)
	}
}

func TestImportLibrary_MultipleAccounts(t *testing.T) {
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()
	if err := db.Migrate(database); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	ctx := context.Background()

	// Both accounts have A1 and A2
	importLibrary(ctx, database, 1, makeBooks("A1", "A2"))
	importLibrary(ctx, database, 2, makeBooks("A1", "A2"))

	// Account 1 loses A2 — account 2 should be unaffected
	importLibrary(ctx, database, 1, makeBooks("A1"))

	if got := countDeleted(t, database, 1); got != 1 {
		t.Errorf("account 1: want 1 deleted, got %d", got)
	}
	if got := countDeleted(t, database, 2); got != 0 {
		t.Errorf("account 2: want 0 deleted (unaffected), got %d", got)
	}
}
