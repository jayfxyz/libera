"""One download job: fetch, decrypt, embed chapters, write companion files."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx
from opentelemetry.trace import Status, StatusCode

from .. import library
from ..audible_api.auth import APP_USER_AGENT
from ..audible_api.client import AudibleClient
from ..audible_api.content import ContentError
from ..db import Database
from ..telemetry import tracer
from .chapters import split_into_chapters
from .ffmpeg import decrypt_args
from .filename import FilenameData, book_directory, render_filename
from .outline import build_outline, ffmetadata, write_outline_files
from .process import run
from .queue import DownloadJob, DownloadQueue

log = logging.getLogger(__name__)

MIN_AUDIOBOOK_BYTES = 1024 * 1024
# Work files live on the same drive as the library, in a folder rescans skip.
INCOMPLETE_DIR = ".incomplete"
# The name Audiobookshelf, Jellyfin and Plex look for in a book's folder.
COVER_FILE_NAME = "cover.jpg"


class JobFailed(Exception):
    """Ends the job with this user-facing message."""


def tiny_download_error(size: int, body: str, license_denied: str) -> str:
    """Explain a download too small to be an audiobook.

    When Audible refused the AAXC license, the AAX fallback typically answers
    with a short error ("No Library Record Found" for newer titles) that hides
    the real cause, so the license reason leads.
    """
    body = body.strip()
    if license_denied:
        return f"{license_denied} (fallback AAX download also failed: {body})"
    return f"download returned {size} bytes (expected an audiobook file): {body}"


def make_runner(db: Database, audible: AudibleClient):
    async def run_job(queue: DownloadQueue, job: DownloadJob) -> None:
        with tracer.start_as_current_span("job.process", attributes={
            "job.id": job.id, "job.asin": job.audible_id, "job.title": job.title, "job.format": job.format,
        }) as span:
            work_dir = os.path.join(job.output_dir, INCOMPLETE_DIR)
            work_files: list[str] = []
            try:
                if job.kind == "pdf":
                    out_file = await _process_pdf_only(queue, job, audible)
                else:
                    out_file = await _process(queue, job, db, audible, work_dir, work_files)
            except JobFailed as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                log.warning("job %s failed: %s", job.id, e)
                queue.set_status(job.id, "error", 0, str(e))
                if job.kind == "audio":  # a missing PDF says nothing about the audiobook
                    await asyncio.to_thread(library.mark_error, db, job.book_id)
                return
            finally:
                for f in work_files:
                    _remove(f)
                _remove_dir_if_empty(work_dir)
            log.info("job %s done: %s", job.id, out_file)
            queue.set_status(job.id, "done", 100, out_file)

    return run_job


async def _process(queue: DownloadQueue, job: DownloadJob, db: Database, audible: AudibleClient,
                   work_dir: str, work_files: list[str]) -> str:
    queue.set_status(job.id, "downloading", 0)

    try:
        info = await audible.get_download_info(job.audible_account_id, job.audible_id)
    except ContentError as e:
        raise JobFailed(f"get download info: {e}")
    if info.format == "aaxc" and not (info.key and info.iv):
        raise JobFailed("missing AAXC decryption key/iv")
    if info.format == "aax" and not info.activation_bytes:
        raise JobFailed("no activation bytes — account not fully authorized")

    os.makedirs(work_dir, exist_ok=True)
    src = os.path.join(work_dir, f"{job.id}.{info.format}")
    work_files.append(src)

    with tracer.start_as_current_span("job.download", attributes={"download.aaxc": info.format == "aaxc"}):
        try:
            await _stream_download(info.download_url, src,
                                   lambda pct: queue.set_status(job.id, "downloading", pct))
        except httpx.HTTPError as e:
            raise JobFailed(f"download: {e}")

    size = os.path.getsize(src)
    log.info("job %s: downloaded %d bytes", job.id, size)
    if size < MIN_AUDIOBOOK_BYTES:
        with open(src, "rb") as f:
            snippet = f.read(512).decode(errors="replace")
        raise JobFailed(tiny_download_error(size, snippet, info.license_denied))

    queue.set_status(job.id, "decrypting", 100)

    book_dir, base_name = _paths(job)
    out_file = os.path.join(book_dir, f"{base_name}.{job.format}")
    try:
        os.makedirs(book_dir, exist_ok=True)
    except OSError as e:
        raise JobFailed(f"mkdir: {e}")

    # Audible's chapter outline (real titles, accurate timings), embedded during
    # decryption. Best-effort: without it the file keeps the Audible file's chapters.
    chapter_info, chapters = await _fetch_outline(audible, job)
    chapters_file = ""
    if chapters:
        chapters_file = os.path.join(work_dir, f"{job.id}.ffmetadata")
        work_files.append(chapters_file)
        with open(chapters_file, "w", encoding="utf-8") as f:
            f.write(ffmetadata(chapters))

    # Cover art: embedded in the audio and saved as cover.jpg for media servers.
    cover_file = ""
    cover = await _fetch_cover(info.cover_url, job.id)
    if cover:
        cover_file = os.path.join(work_dir, f"{job.id}.cover.jpg")
        work_files.append(cover_file)
        with open(cover_file, "wb") as f:
            f.write(cover)

    # Decrypt next to the source, then move into place: a failed or cancelled
    # job never leaves a partial audiobook in the library.
    decrypted = os.path.join(work_dir, f"{job.id}.out.{job.format}")
    work_files.append(decrypted)
    with tracer.start_as_current_span("job.ffmpeg", attributes={"ffmpeg.format": job.format}) as span:
        code, _, err = await run(decrypt_args(info, src, decrypted, job.format, chapters_file, cover_file))
        if code != 0:
            message = err.decode(errors="replace").strip()[-1000:]
            span.set_status(Status(StatusCode.ERROR, message))
            raise JobFailed(f"ffmpeg: {message}")
    os.replace(decrypted, out_file)
    if cover:
        try:
            with open(os.path.join(book_dir, COVER_FILE_NAME), "wb") as f:
                f.write(cover)
        except OSError as e:
            log.warning("job %s: saving cover failed (non-fatal): %s", job.id, e)

    if chapters:
        try:
            write_outline_files(out_file, job.audible_id, job.title, chapter_info, chapters)
        except OSError as e:
            log.warning("job %s: writing chapter outline failed (non-fatal): %s", job.id, e)

    if job.split_chapters:
        queue.set_status(job.id, "decrypting", 100, "splitting chapters…")
        try:
            await split_into_chapters(out_file, book_dir, base_name, f".{job.format}")
        except Exception as e:
            log.warning("job %s: chapter split failed (non-fatal): %s", job.id, e)

    await asyncio.to_thread(library.mark_downloaded, db, job.book_id, job.format, out_file)

    # Companion PDF: best-effort, doesn't affect the job.
    if job.include_pdf:
        try:
            pdf = await audible.get_pdf(job.audible_account_id, job.audible_id)
            if pdf:
                with open(os.path.join(book_dir, f"{base_name}.pdf"), "wb") as f:
                    f.write(pdf)
        except Exception as e:
            log.warning("job %s: PDF download failed (non-fatal): %s", job.id, e)

    return out_file


def _paths(job: DownloadJob) -> tuple[str, str]:
    """(book folder, file name without extension) for a job."""
    names = FilenameData(
        title=job.title, authors=job.authors, narrators=job.narrators, series_name=job.series_name,
        series_index=job.series_index, year=job.year, language=job.language, duration_h=job.duration_h,
    )
    return book_directory(job.output_dir, job.folder_template, names), render_filename(job.filename_template, names)


async def _process_pdf_only(queue: DownloadQueue, job: DownloadJob, audible: AudibleClient) -> str:
    """Save just the companion PDF into the book's folder (no license request)."""
    queue.set_status(job.id, "downloading", 0)
    try:
        pdf = await audible.get_pdf(job.audible_account_id, job.audible_id)
    except ContentError as e:
        raise JobFailed(f"PDF: {e}")
    if not pdf:
        raise JobFailed("This title has no companion PDF")
    book_dir, base_name = _paths(job)
    out_file = os.path.join(book_dir, f"{base_name}.pdf")
    try:
        os.makedirs(book_dir, exist_ok=True)
        with open(out_file, "wb") as f:
            f.write(pdf)
    except OSError as e:
        raise JobFailed(f"saving PDF: {e}")
    return out_file


async def _fetch_outline(audible: AudibleClient, job: DownloadJob) -> tuple[dict[str, Any] | None, list]:
    with tracer.start_as_current_span("job.chapters") as span:
        try:
            info = await audible.get_chapter_info(job.audible_account_id, job.audible_id)
        except Exception as e:
            log.warning("job %s: chapter outline unavailable (non-fatal): %s", job.id, e)
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            return None, []
        chapters = build_outline(info)
        span.set_attribute("chapters.count", len(chapters))
        return info, chapters


async def _fetch_cover(url: str, job_id: str) -> bytes | None:
    """The cover image, or None if there's none or it can't be fetched (best-effort)."""
    if not url:
        return None
    try:
        data = await _fetch_bytes(url)
    except httpx.HTTPError as e:
        log.warning("job %s: cover download failed (non-fatal): %s", job_id, e)
        return None
    if not data.startswith(b"\xff\xd8"):  # embedding copies the stream, so it must be JPEG
        log.warning("job %s: cover is not a JPEG, skipping", job_id)
        return None
    return data


async def _fetch_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _stream_download(url: str, dest: str, on_progress) -> None:
    timeout = httpx.Timeout(60.0, connect=30.0)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout,
                                 headers={"User-Agent": APP_USER_AGENT}) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            done = 0
            last = time.monotonic()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total and time.monotonic() - last > 0.5:
                        on_progress(done / total * 100)
                        last = time.monotonic()


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _remove_dir_if_empty(path: str) -> None:
    try:
        os.rmdir(path)
    except OSError:
        pass
