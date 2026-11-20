"""updated_at on downloads and library_books.

Clients get the same resource from a snapshot (REST) and from events; when
the two cross, updated_at says which copy is newer. Existing rows get a
best guess (SQLite can't add a column with a non-constant default).

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("downloads", sa.Column("updated_at", sa.String))
    op.add_column("library_books", sa.Column("updated_at", sa.String))
    op.execute("UPDATE downloads SET updated_at = COALESCE(finished_at, started_at, created_at)")
    op.execute("UPDATE library_books SET updated_at = COALESCE(last_downloaded, CURRENT_TIMESTAMP)")


def downgrade() -> None:
    op.execute("ALTER TABLE library_books DROP COLUMN updated_at")  # SQLite >= 3.35; batch mode would rebuild
    op.execute("ALTER TABLE downloads DROP COLUMN updated_at")
