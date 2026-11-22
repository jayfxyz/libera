"""tasks.not_before: workers don't claim a pending task before this time (retry backoff, snooze).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("not_before", sa.String))


def downgrade() -> None:
    op.execute("ALTER TABLE tasks DROP COLUMN not_before")  # SQLite >= 3.35; batch mode would rebuild
