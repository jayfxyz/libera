"""downloads.status: add decrypt_queued (fetched, waiting for a decrypt worker).

Until now that state was `queued` at 100%.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

BEFORE = ("queued", "downloading", "decrypting", "done", "failed", "cancelled")
AFTER = ("queued", "downloading", "decrypt_queued", "decrypting", "done", "failed", "cancelled")


def _enum(values):
    return sa.Enum(*values, name="download_status", native_enum=False, create_constraint=True)


def _set_status_values(values) -> None:
    """Rebuild the table (SQLite) with the CHECK of `values`."""
    with op.batch_alter_table("downloads") as batch:
        batch.drop_constraint("download_status", type_="check")
        batch.alter_column("status", type_=_enum(values), existing_nullable=False)


def upgrade() -> None:
    _set_status_values(AFTER)
    op.execute("UPDATE downloads SET status = 'decrypt_queued' WHERE status = 'queued' AND percent >= 100")


def downgrade() -> None:
    op.execute("UPDATE downloads SET status = 'queued' WHERE status = 'decrypt_queued'")
    _set_status_values(BEFORE)
