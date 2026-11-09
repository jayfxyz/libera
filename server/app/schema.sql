-- Audible accounts
CREATE TABLE IF NOT EXISTS accounts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name         TEXT NOT NULL,
    email                TEXT NOT NULL UNIQUE,
    locale               TEXT NOT NULL,
    audible_account_id   TEXT NOT NULL DEFAULT '',
    library_scan_enabled INTEGER NOT NULL DEFAULT 1,
    last_scanned_at      DATETIME,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Audiobook metadata (immutable Audible data)
CREATE TABLE IF NOT EXISTS books (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    audible_id           TEXT NOT NULL UNIQUE,
    title                TEXT NOT NULL,
    subtitle             TEXT,
    description          TEXT,
    length_minutes       INTEGER NOT NULL DEFAULT 0,
    content_type         TEXT NOT NULL DEFAULT 'Product',
    locale               TEXT NOT NULL,
    is_abridged          INTEGER NOT NULL DEFAULT 0,
    is_spatial           INTEGER NOT NULL DEFAULT 0,
    date_published       DATETIME,
    language             TEXT,
    cover_url            TEXT,
    publisher            TEXT,
    audible_rating       REAL,
    audible_rating_count INTEGER,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Account <-> Book link with per-user state
CREATE TABLE IF NOT EXISTS library_books (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id            INTEGER NOT NULL REFERENCES books(id),
    account_id         INTEGER NOT NULL REFERENCES accounts(id),
    date_added         DATETIME NOT NULL,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    is_audible_plus    INTEGER NOT NULL DEFAULT 0,
    liberation_status  TEXT NOT NULL DEFAULT 'not_liberated',
    tags               TEXT NOT NULL DEFAULT '',
    user_rating        REAL,
    is_finished        INTEGER NOT NULL DEFAULT 0,
    last_downloaded    DATETIME,
    last_format        TEXT,
    is_hidden          INTEGER NOT NULL DEFAULT 0,  -- hidden from the library by the user
    file_path          TEXT,                        -- where the last download was saved
    UNIQUE(book_id, account_id)
);

-- Authors, narrators, publishers
CREATE TABLE IF NOT EXISTS contributors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    audible_id      TEXT,
    name            TEXT NOT NULL,
    UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS book_contributors (
    book_id         INTEGER NOT NULL REFERENCES books(id),
    contributor_id  INTEGER NOT NULL REFERENCES contributors(id),
    role            TEXT NOT NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (book_id, contributor_id, role)
);

-- Series
CREATE TABLE IF NOT EXISTS series (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    audible_id      TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS series_books (
    series_id       INTEGER NOT NULL REFERENCES series(id),
    book_id         INTEGER NOT NULL REFERENCES books(id),
    book_index      TEXT,
    PRIMARY KEY (series_id, book_id)
);

-- Categories
CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    audible_id      TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    parent_id       INTEGER REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS book_categories (
    book_id         INTEGER NOT NULL REFERENCES books(id),
    category_id     INTEGER NOT NULL REFERENCES categories(id),
    PRIMARY KEY (book_id, category_id)
);

-- User-configurable application settings (key-value store)
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Full-text search (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    title,
    subtitle,
    description,
    authors,
    narrators,
    series_name,
    tags,
    content='',
    contentless_delete=1
);
