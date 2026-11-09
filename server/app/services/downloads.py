"""Queueing downloads: turning a book and options into a job."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from ..config import FORMATS, Config
from ..db import Database
from ..jobs.queue import DownloadJob, DownloadQueue
from ..telemetry import tracer
from . import library

KINDS = ("audio", "pdf")  # audio: the audiobook (+ companion PDF); pdf: only the companion PDF


class InvalidOptions(ValueError):
    pass


@dataclass
class DownloadOptions:
    format: str = ""  # m4b/mp3; "" = the default from Settings
    split_chapters: bool = False
    include_pdf: bool = True  # save the companion PDF next to the audiobook, if there is one
    kind: str = "audio"


def _format(opts: DownloadOptions, config: Config) -> str:
    fmt = opts.format or config.default_format
    if fmt not in FORMATS:
        raise InvalidOptions("format must be 'm4b' or 'mp3'")
    if opts.kind not in KINDS:
        raise InvalidOptions("kind must be 'audio' or 'pdf'")
    return fmt


def _job(meta: dict, book_id: int, fmt: str, opts: DownloadOptions, config: Config) -> DownloadJob:
    settings = config.snapshot()  # later setting changes don't affect a queued job
    return DownloadJob(
        id=f"dl-{book_id}-{time.time_ns() // 1000}",
        book_id=book_id,
        audible_id=meta["audible_id"],
        account_id=meta["account_id"],
        audible_account_id=meta["audible_account_id"],
        format=fmt,
        output_dir=settings.output_dir,
        filename_template=settings.filename_template,
        folder_template=settings.folder_template,
        split_chapters=opts.split_chapters,
        include_pdf=opts.include_pdf,
        kind=opts.kind,
        **library.naming_data(meta),
    )


def _enqueue(queue: DownloadQueue, job: DownloadJob) -> None:
    with tracer.start_as_current_span("job.enqueue", attributes={
        "job.id": job.id, "job.asin": job.audible_id, "job.format": job.format, "job.kind": job.kind,
    }):
        queue.enqueue(job)


async def enqueue(db: Database, queue: DownloadQueue, config: Config, book_id: int,
                  opts: DownloadOptions, account_id: int | None = None) -> str | None:
    """Queue one book. Returns the job id, or None if the book isn't in that library."""
    fmt = _format(opts, config)
    meta = await asyncio.to_thread(library.book_meta, db, book_id, account_id)
    if meta is None:
        return None
    job = _job(meta, book_id, fmt, opts, config)
    _enqueue(queue, job)
    return job.id


async def enqueue_many(db: Database, queue: DownloadQueue, config: Config, book_ids: list[int],
                       opts: DownloadOptions) -> list[dict]:
    """Queue several books in the order given; duplicates and unknown ids are skipped."""
    fmt = _format(opts, config)
    queued = []
    for book_id in dict.fromkeys(book_ids):
        meta = await asyncio.to_thread(library.book_meta, db, book_id, None)
        if meta is not None:
            job = _job(meta, book_id, fmt, opts, config)
            _enqueue(queue, job)
            queued.append({"job_id": job.id, "book_id": book_id})
    return queued
