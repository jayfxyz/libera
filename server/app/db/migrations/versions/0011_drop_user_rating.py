"""library_books.user_rating is dropped: nothing in the UI set or showed it.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE library_books DROP COLUMN user_rating")  # SQLite >= 3.35; batch mode would rebuild


def downgrade() -> None:
    op.execute("ALTER TABLE library_books ADD COLUMN user_rating REAL")
