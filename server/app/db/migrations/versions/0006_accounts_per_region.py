"""One account per Amazon login and region.

The same Amazon login can be added once per region (as Libation allows):
accounts are unique by (email, locale) instead of by email. SQLite can't
change a table's constraints in place, so the table is rebuilt; app.db.migrate
runs migrations with foreign keys off, as that requires.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

COLUMNS = "id, account_name, email, locale, audible_account_id, library_scan_enabled, last_scanned_at, created_at"


def _rebuild(unique: str) -> None:
    conn = op.get_bind()
    seq = conn.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name = 'accounts'").scalar()
    op.execute(f"""
        CREATE TABLE accounts_new (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name         TEXT NOT NULL,
            email                TEXT NOT NULL,
            locale               TEXT NOT NULL,
            audible_account_id   TEXT NOT NULL DEFAULT '',
            library_scan_enabled INTEGER NOT NULL DEFAULT 1,
            last_scanned_at      DATETIME,
            created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE ({unique})
        )""")
    op.execute(f"INSERT INTO accounts_new ({COLUMNS}) SELECT {COLUMNS} FROM accounts")
    op.execute("DROP TABLE accounts")
    op.execute("ALTER TABLE accounts_new RENAME TO accounts")
    if seq is not None:  # ids of removed accounts aren't handed out again
        op.execute(f"UPDATE sqlite_sequence SET seq = MAX(seq, {int(seq)}) WHERE name = 'accounts'")


def upgrade() -> None:
    _rebuild("email, locale")


def downgrade() -> None:
    # Fails if one login was added in two regions: remove one of them first.
    _rebuild("email")
