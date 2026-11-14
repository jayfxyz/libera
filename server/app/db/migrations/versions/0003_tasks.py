"""Generic task queue.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Text, primary_key=True),  # uuid4 hex
        sa.Column("type", sa.Text, nullable=False),  # task name, e.g. "download_book"
        sa.Column("payload", sa.Text, nullable=False),  # JSON, validated by the task's pydantic model
        sa.Column("status", sa.Text, nullable=False),  # pending | processing | completed | failed | cancelled
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.String, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("locked_at", sa.String),
        sa.Column("finished_at", sa.String),
    )
    op.create_index("ix_tasks_status_created", "tasks", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_status_created", "tasks")
    op.drop_table("tasks")
