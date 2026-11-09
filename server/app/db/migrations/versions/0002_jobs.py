"""Persistent background jobs (download queue and history).

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("type", sa.Text, nullable=False),  # "download"; room for other background work
        sa.Column("status", sa.Text, nullable=False),  # queued | downloading | decrypting | done | error
        sa.Column("percent", sa.Float, nullable=False, server_default="0"),
        sa.Column("message", sa.Text),
        sa.Column("title", sa.Text),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="SET NULL")),
        sa.Column("payload", sa.Text, nullable=False),  # JSON: what's needed to run (or re-run) the job
        sa.Column("created_at", sa.String, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.String),
        sa.Column("finished_at", sa.String),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_status_created", "jobs")
    op.drop_table("jobs")
