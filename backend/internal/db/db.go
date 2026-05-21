package db

import (
	"database/sql"
	_ "embed"
	"fmt"
	"os"
	"path/filepath"

	_ "modernc.org/sqlite"
)

//go:embed schema.sql
var schema string

func Open(path string) (*sql.DB, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return nil, fmt.Errorf("create db directory: %w", err)
	}

	db, err := sql.Open("sqlite", path+"?_journal_mode=WAL&_foreign_keys=on")
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}

	db.SetMaxOpenConns(1) // SQLite WAL supports 1 writer
	db.SetMaxIdleConns(1)

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping sqlite: %w", err)
	}

	return db, nil
}

func Migrate(db *sql.DB) error {
	if _, err := db.Exec(schema); err != nil {
		return fmt.Errorf("run schema: %w", err)
	}
	// Best-effort column additions for existing databases (SQLite has no IF NOT EXISTS for ALTER TABLE).
	db.Exec(`ALTER TABLE accounts ADD COLUMN last_scanned_at DATETIME`)
	return nil
}

func OpenMemory() (*sql.DB, error) {
	db, err := sql.Open("sqlite", ":memory:?_foreign_keys=on")
	if err != nil {
		return nil, fmt.Errorf("open in-memory sqlite: %w", err)
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping in-memory sqlite: %w", err)
	}
	return db, nil
}
