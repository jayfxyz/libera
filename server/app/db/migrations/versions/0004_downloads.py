"""Downloads table, books.has_pdf, tasks.status as an enum.

Finished audio jobs become downloads (their output path gives path and
base_name). Other jobs (PDF-only, failed, cancelled, unfinished) recorded no
path and are dropped, as is the jobs table. Downgrading recreates an empty
jobs table: history is not restored.

Revision ID: 0004
Revises: 0003
"""

import json
import os

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TASK_STATUSES = ("pending", "processing", "completed", "failed", "cancelled")
FORMATS = ("m4b", "mp3")
DOWNLOAD_STATUSES = ("queued", "downloading", "decrypting", "done", "failed", "cancelled")


def _enum(values, name):
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    # Before `downloads` exists: SQLite rebuilds the table to add the CHECK.
    with op.batch_alter_table("tasks") as batch:
        batch.alter_column("status", type_=_enum(TASK_STATUSES, "task_status"), existing_nullable=False)

    op.create_table(
        "downloads",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("library_book_id", sa.Integer, sa.ForeignKey("library_books.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("format", _enum(FORMATS, "download_format"), nullable=False),
        sa.Column("split_chapters", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("path", sa.Text, nullable=False),  # the book's folder (absolute)
        sa.Column("base_name", sa.Text, nullable=False),  # file name without extension
        sa.Column("status", _enum(DOWNLOAD_STATUSES, "download_status"), nullable=False),
        sa.Column("percent", sa.Float, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column("files", sa.Text),  # JSON [{role, name, size_bytes}], written when done
        sa.Column("task_id", sa.Text, sa.ForeignKey("tasks.id", ondelete="SET NULL")),  # current task
        sa.Column("created_at", sa.String, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.String),
        sa.Column("finished_at", sa.String),
    )
    op.create_index("ix_downloads_status_created", "downloads", ["status", "created_at"])
    op.create_index("ix_downloads_library_book", "downloads", ["library_book_id"])

    op.add_column("books", sa.Column("has_pdf", sa.Boolean))  # NULL: not synced since this column existed

    conn = op.get_bind()
    finished = conn.execute(sa.text("""
        SELECT j.id, lb.id AS library_book_id, j.payload, j.message AS audio,
               j.created_at, j.started_at, j.finished_at
        FROM jobs j
        JOIN library_books lb ON lb.book_id = json_extract(j.payload, '$.book_id')
                             AND lb.account_id = json_extract(j.payload, '$.account_id')
        WHERE j.status = 'done' AND j.message IS NOT NULL
          AND COALESCE(json_extract(j.payload, '$.kind'), 'audio') = 'audio'
    """)).mappings().all()
    for job in finished:
        payload = json.loads(job["payload"])
        stem, ext = os.path.splitext(os.path.basename(job["audio"]))  # e.g. ".../Title.m4b"
        fmt = payload.get("format") or ext[1:]
        if fmt not in FORMATS:
            continue
        conn.execute(sa.text("""
            INSERT INTO downloads (id, library_book_id, format, split_chapters, path, base_name, status,
                                   percent, created_at, started_at, finished_at)
            VALUES (:id, :lb, :fmt, :split, :path, :base, 'done', 100, :created, :started, :finished)
        """), {"id": job["id"], "lb": job["library_book_id"], "fmt": fmt,
               "split": bool(payload.get("split_chapters")), "path": os.path.dirname(job["audio"]),
               "base": stem, "created": job["created_at"], "started": job["started_at"],
               "finished": job["finished_at"]})

    op.drop_index("ix_jobs_status_created", "jobs")
    op.drop_table("jobs")


def downgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("percent", sa.Float, nullable=False, server_default="0"),
        sa.Column("message", sa.Text),
        sa.Column("title", sa.Text),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="SET NULL")),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("created_at", sa.String, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.String),
        sa.Column("finished_at", sa.String),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.execute("ALTER TABLE books DROP COLUMN has_pdf")  # SQLite >= 3.35; batch mode would rebuild books
    op.drop_index("ix_downloads_library_book", "downloads")
    op.drop_index("ix_downloads_status_created", "downloads")
    op.drop_table("downloads")
    with op.batch_alter_table("tasks") as batch:
        batch.alter_column("status", type_=sa.Text, existing_type=_enum(TASK_STATUSES, "task_status"),
                           existing_nullable=False)  # existing_type: drops the enum's CHECK too
