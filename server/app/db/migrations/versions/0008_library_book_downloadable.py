"""library_books.is_downloadable: whether Audible grants offline download rights for this entry.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("library_books", sa.Column("is_downloadable", sa.Integer, nullable=False, server_default="1"))


def downgrade() -> None:
    op.execute("ALTER TABLE library_books DROP COLUMN is_downloadable")
