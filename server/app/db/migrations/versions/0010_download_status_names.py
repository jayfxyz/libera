"""library_books.liberation_status becomes download_status, with the values "downloaded" and "not_downloaded".

The values were the historical "liberated" and "not_liberated". SQLite can't change a column's default in
place, so the table is rebuilt; app.db.migrate runs migrations with foreign keys off, as that requires.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

OTHER_COLUMNS = ("id, book_id, account_id, date_added, is_deleted, is_audible_plus, tags, user_rating, is_finished, "
                 "last_downloaded, last_format, is_hidden, file_path, updated_at, is_downloadable")


def _rebuild(*, old: str, new: str, default: str) -> None:
    """Rename the status column `old` to `new` with a new default, keeping rows, constraints and the id counter."""
    conn = op.get_bind()
    seq = conn.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name = 'library_books'").scalar()
    op.execute(f"""
        CREATE TABLE library_books_new (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id            INTEGER NOT NULL REFERENCES books(id),
            account_id         INTEGER NOT NULL REFERENCES accounts(id),
            date_added         DATETIME NOT NULL,
            is_deleted         INTEGER NOT NULL DEFAULT 0,
            is_audible_plus    INTEGER NOT NULL DEFAULT 0,
            {new}  TEXT NOT NULL DEFAULT '{default}',
            tags               TEXT NOT NULL DEFAULT '',
            user_rating        REAL,
            is_finished        INTEGER NOT NULL DEFAULT 0,
            last_downloaded    DATETIME,
            last_format        TEXT,
            is_hidden          INTEGER NOT NULL DEFAULT 0,
            file_path          TEXT,
            updated_at         VARCHAR,
            is_downloadable    INTEGER NOT NULL DEFAULT 1,
            UNIQUE(book_id, account_id)
        )""")
    op.execute(f"INSERT INTO library_books_new ({OTHER_COLUMNS}, {new}) "
               f"SELECT {OTHER_COLUMNS}, {old} FROM library_books")
    op.execute("DROP TABLE library_books")
    op.execute("ALTER TABLE library_books_new RENAME TO library_books")
    if seq is not None:  # ids of removed rows aren't handed out again
        op.execute("DELETE FROM sqlite_sequence WHERE name = 'library_books'")
        op.execute(f"INSERT INTO sqlite_sequence (name, seq) VALUES ('library_books', {int(seq)})")


def upgrade() -> None:
    _rebuild(old="liberation_status", new="download_status", default="not_downloaded")
    op.execute("UPDATE library_books SET download_status = 'downloaded' WHERE download_status = 'liberated'")
    op.execute("UPDATE library_books SET download_status = 'not_downloaded' "
               "WHERE download_status = 'not_liberated'")


def downgrade() -> None:
    op.execute("UPDATE library_books SET download_status = 'liberated' WHERE download_status = 'downloaded'")
    op.execute("UPDATE library_books SET download_status = 'not_liberated' "
               "WHERE download_status = 'not_downloaded'")
    _rebuild(old="download_status", new="liberation_status", default="not_liberated")
