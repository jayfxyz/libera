"""The download pipeline, in two steps that know nothing about tasks or the database.

- fetch: everything that needs Audible. The license, the encrypted file and
  the extras (cover, chapter outline, companion PDF) go into the work folder
  as a FetchedBundle.
- decrypt: local only. ffmpeg (chapters and cover embedded), move into
  place, then the extras next to the audiobook. Returns the files written.

Between the two steps the bundle waits in the work folder, so a failed
decrypt can be retried without downloading again.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from opentelemetry.trace import Status, StatusCode

from ..audible_api.auth import APP_USER_AGENT
from ..audible_api.client import AudibleClient
from ..audible_api.content import ContentError, DownloadInfo
from ..telemetry import tracer
from .chapters import split_into_chapters
from .ffmpeg import decrypt_args
from .outline import build_outline, ffmetadata, write_outline_files
from .process import run

log = logging.getLogger(__name__)

MIN_AUDIOBOOK_BYTES = 1024 * 1024
# Work files live on the same drive as the library, in a folder rescans skip.
INCOMPLETE_DIR = ".incomplete"
# The name Audiobookshelf, Jellyfin and Plex look for in a book's folder.
COVER_FILE_NAME = "cover.jpg"
# What decrypting needs, saved beside the encrypted file.
_LICENSE_FIELDS = ("format", "codec", "key", "iv", "activation_bytes", "cover_url")

Progress = Callable[..., None]  # report_progress(status, percent, detail="")
Written = list[tuple[str, str]]  # (role, path) of files written


class DownloadFailed(Exception):
    """Ends the step with this user-facing message. `retry`: worth trying
    again as is (a network error), unlike a refusal or a broken file."""

    def __init__(self, message: str, retry: bool = False):
        super().__init__(message)
        self.retry = retry


@dataclass
class Target:
    """One download, as the pipeline sees it."""

    download_id: str
    audible_account_id: str  # token file key
    audible_id: str  # ASIN
    title: str
    format: str  # m4b | mp3
    split_chapters: bool
    path: str  # the book's folder
    base_name: str  # file name without extension
    has_pdf: bool | None  # None: unknown, so try


@dataclass
class FileEntry:
    role: str  # audio | chapter | pdf | cover | metadata
    name: str  # within Target.path
    size_bytes: int


@dataclass
class FetchedBundle:
    """What a completed fetch left in the work folder for decrypt."""

    source: str  # the encrypted file
    info: DownloadInfo  # format, keys, codec
    cover: str | None  # JPEG, if Audible had one
    chapter_info: dict[str, Any] | None  # Audible's chapter outline, if available
    pdf: str | None  # the companion PDF, if any


# --- step 1: fetch (everything that needs Audible) ---------------------------------------

async def fetch(audible: AudibleClient, t: Target, work_dir: str, report_progress: Progress) -> None:
    """Download the encrypted file, what decrypting it needs, and the extras
    (cover, chapter outline, companion PDF) into the work folder. On any
    failure (or cancellation) nothing is left behind."""
    with _traced_step("download.fetch", t):
        report_progress("downloading", 0)
        info = await _request_license(audible, t)
        try:
            partial = await _download_encrypted(info, t, work_dir, report_progress)
            _check_is_audiobook(partial, info)
            await _fetch_extras(audible, t, info, work_dir)
            _save_license(work_dir, t.download_id, info)
            _keep_source(partial)  # last: its presence means the fetch is complete
        except BaseException:
            discard_bundle(work_dir, t.download_id)
            raise


# --- step 2: decrypt (local only, no network) --------------------------------------------

async def decrypt(t: Target, work_dir: str, report_progress: Progress) -> list[FileEntry]:
    """Decrypt the fetched bundle into the book's folder and put the extras
    next to it; returns every file written. Needs no network, so a failed
    decrypt can be retried freely. The bundle stays: the caller discards it on success."""
    with _traced_step("download.decrypt", t):
        bundle = _require_bundle(work_dir, t)
        report_progress("decrypting", 100)
        _make_folder(t.path)
        chapters = build_outline(bundle.chapter_info) if bundle.chapter_info else []

        audio = await _decrypt_audio(bundle, chapters, t, work_dir)
        written: Written = [("audio", audio)]
        written += _place_cover(bundle, t)
        written += _write_chapter_files(bundle, chapters, t, audio)
        if t.split_chapters:
            report_progress("decrypting", 100, "splitting chapters…")
            written += await _split(t, audio)
        written += _place_pdf(bundle, t)
        return _manifest(t, written)


# --- the work folder between the two steps ------------------------------------------------

def read_fetched_bundle(work_dir: str, download_id: str) -> FetchedBundle | None:
    """What a completed fetch left, or None (never fetched, or cleaned up)."""
    try:
        with open(_work_file(work_dir, download_id, "license.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    source = _work_file(work_dir, download_id, data.get("format", ""))
    if not os.path.isfile(source):
        return None
    chapter_info = None
    try:
        with open(_work_file(work_dir, download_id, "outline.json"), encoding="utf-8") as f:
            chapter_info = json.load(f)
    except (OSError, ValueError):
        pass
    return FetchedBundle(
        source=source,
        info=DownloadInfo(download_url="", **{k: data.get(k) or "" for k in _LICENSE_FIELDS}),
        cover=_existing(_work_file(work_dir, download_id, "cover.jpg")),
        chapter_info=chapter_info,
        pdf=_existing(_work_file(work_dir, download_id, "pdf")),
    )


def discard_bundle(work_dir: str, download_id: str) -> None:
    """Delete everything a download left in the work folder."""
    try:
        names = os.listdir(work_dir)
    except FileNotFoundError:
        return
    for name in names:
        if name.startswith(f"{download_id}."):
            _remove(os.path.join(work_dir, name))
    _remove_dir_if_empty(work_dir)


def prune_work_dir(work_dir: str, max_age_s: float) -> int:
    """Delete work files older than max_age_s (bundles nobody retried).
    Returns how many were deleted."""
    try:
        names = os.listdir(work_dir)
    except FileNotFoundError:
        return 0
    cutoff, deleted = time.time() - max_age_s, 0
    for name in names:
        path = os.path.join(work_dir, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
        except OSError as e:
            log.warning("could not delete old work file %s: %s", path, e)
    _remove_dir_if_empty(work_dir)
    return deleted


# --- fetch, in detail ----------------------------------------------------------------------

async def _request_license(audible: AudibleClient, t: Target) -> DownloadInfo:
    try:
        info = await audible.get_download_info(t.audible_account_id, t.audible_id)
    except ContentError as e:
        raise DownloadFailed(f"get download info: {e}")
    if info.format == "aaxc" and not (info.key and info.iv):
        raise DownloadFailed("missing AAXC decryption key/iv")
    if info.format == "aax" and not info.activation_bytes:
        raise DownloadFailed("no activation bytes — account not fully authorized")
    return info


async def _download_encrypted(info: DownloadInfo, t: Target, work_dir: str, report_progress: Progress) -> str:
    """Stream the encrypted file to <id>.<format>.part; returns that path."""
    os.makedirs(work_dir, exist_ok=True)
    partial = _work_file(work_dir, t.download_id, f"{info.format}.part")
    try:
        await _stream_download(info.download_url, partial, lambda pct: report_progress("downloading", pct))
    except httpx.HTTPError as e:
        raise DownloadFailed(f"download: {e}", retry=True)
    log.info("download %s: %d bytes", t.download_id, os.path.getsize(partial))
    return partial


def _check_is_audiobook(path: str, info: DownloadInfo) -> None:
    size = os.path.getsize(path)
    if size < MIN_AUDIOBOOK_BYTES:
        with open(path, "rb") as f:
            snippet = f.read(512).decode(errors="replace")
        raise DownloadFailed(tiny_download_error(size, snippet, info.license_denied))


async def _fetch_extras(audible: AudibleClient, t: Target, info: DownloadInfo, work_dir: str) -> None:
    """Cover, chapter outline and companion PDF. Each is best-effort: a missing
    one is simply absent from the work folder."""
    if cover := await _fetch_cover(info.cover_url, t.download_id):
        _write_bytes(_work_file(work_dir, t.download_id, "cover.jpg"), cover)
    if chapter_info := await _fetch_chapter_info(audible, t):
        _write_json(_work_file(work_dir, t.download_id, "outline.json"), chapter_info)
    if t.has_pdf is not False:  # None: not synced yet, so try
        if pdf := await _fetch_pdf(audible, t):
            _write_bytes(_work_file(work_dir, t.download_id, "pdf"), pdf)


def _save_license(work_dir: str, download_id: str, info: DownloadInfo) -> None:
    _write_json(_work_file(work_dir, download_id, "license.json"), {k: getattr(info, k) for k in _LICENSE_FIELDS})


def _keep_source(partial: str) -> None:
    os.replace(partial, partial.removesuffix(".part"))


async def _fetch_chapter_info(audible: AudibleClient, t: Target) -> dict[str, Any] | None:
    """Audible's chapter outline (real titles, accurate timings), or None."""
    with tracer.start_as_current_span("download.chapters") as span:
        try:
            return await audible.get_chapter_info(t.audible_account_id, t.audible_id)
        except Exception as e:
            log.warning("download %s: chapter outline unavailable (non-fatal): %s", t.download_id, e)
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            return None


async def _fetch_pdf(audible: AudibleClient, t: Target) -> bytes | None:
    try:
        return await audible.get_pdf(t.audible_account_id, t.audible_id) or None
    except Exception as e:
        log.warning("download %s: PDF download failed (non-fatal): %s", t.download_id, e)
        return None


async def _fetch_cover(url: str, download_id: str) -> bytes | None:
    """The cover image, or None if there's none or it can't be fetched (best-effort)."""
    if not url:
        return None
    try:
        data = await _fetch_bytes(url)
    except httpx.HTTPError as e:
        log.warning("download %s: cover download failed (non-fatal): %s", download_id, e)
        return None
    if not data.startswith(b"\xff\xd8"):  # embedding copies the stream, so it must be JPEG
        log.warning("download %s: cover is not a JPEG, skipping", download_id)
        return None
    return data


# --- decrypt, in detail --------------------------------------------------------------------

def _require_bundle(work_dir: str, t: Target) -> FetchedBundle:
    if (bundle := read_fetched_bundle(work_dir, t.download_id)) is None:
        raise DownloadFailed("the downloaded file is missing; download again")
    return bundle


def _make_folder(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise DownloadFailed(f"mkdir: {e}")


async def _decrypt_audio(bundle: FetchedBundle, chapters: list, t: Target, work_dir: str) -> str:
    """Decrypt into the work folder with chapters and cover embedded, then move
    into place: a failed or cancelled decrypt never leaves a partial audiobook
    in the library. Returns the audio file's path."""
    temp: list[str] = []
    try:
        chapters_file = ""
        if chapters:
            chapters_file = _work_file(work_dir, t.download_id, "ffmetadata")
            temp.append(chapters_file)
            _write_bytes(chapters_file, ffmetadata(chapters).encode())
        decrypted = _work_file(work_dir, t.download_id, f"out.{t.format}")
        temp.append(decrypted)
        with tracer.start_as_current_span("download.ffmpeg", attributes={"ffmpeg.format": t.format}):
            code, _, err = await run(decrypt_args(bundle.info, bundle.source, decrypted, t.format, chapters_file,
                                                  bundle.cover or ""))
        if code != 0:
            raise DownloadFailed(f"ffmpeg: {err.decode(errors='replace').strip()[-1000:]}")
        audio = os.path.join(t.path, f"{t.base_name}.{t.format}")
        os.replace(decrypted, audio)
        return audio
    finally:
        for f in temp:
            _remove(f)


def _place_cover(bundle: FetchedBundle, t: Target) -> Written:
    """cover.jpg for media servers. Best-effort."""
    return _place(bundle.cover, os.path.join(t.path, COVER_FILE_NAME), "cover", t)


def _place_pdf(bundle: FetchedBundle, t: Target) -> Written:
    """The companion PDF next to the audiobook. Best-effort."""
    return _place(bundle.pdf, os.path.join(t.path, f"{t.base_name}.pdf"), "pdf", t)


def _write_chapter_files(bundle: FetchedBundle, chapters: list, t: Target, audio: str) -> Written:
    """<audio>.cue and <audio>.chapters.json. Best-effort."""
    if not chapters:
        return []
    try:
        return [("metadata", p) for p in
                write_outline_files(audio, t.audible_id, t.title, bundle.chapter_info, chapters)]
    except OSError as e:
        log.warning("download %s: writing chapter outline failed (non-fatal): %s", t.download_id, e)
        return []


async def _split(t: Target, audio: str) -> Written:
    """One file per chapter, next to the full audiobook. Best-effort."""
    try:
        return [("chapter", p) for p in await split_into_chapters(audio, t.path, t.base_name, f".{t.format}")]
    except Exception as e:
        log.warning("download %s: chapter split failed (non-fatal): %s", t.download_id, e)
        return []


def _manifest(t: Target, written: Written) -> list[FileEntry]:
    """Best-effort: a file that can't be measured is left out."""
    entries = []
    for role, path in written:
        try:
            entries.append(FileEntry(role, os.path.relpath(path, t.path), os.path.getsize(path)))
        except OSError as e:
            log.warning("download %s: %s left out of the manifest: %s", t.download_id, path, e)
    return entries


# --- small helpers -------------------------------------------------------------------------

@contextmanager
def _traced_step(name: str, t: Target):
    """A span for one pipeline step; a DownloadFailed marks it as an error."""
    with tracer.start_as_current_span(name, attributes={
        "download.id": t.download_id, "download.asin": t.audible_id, "download.format": t.format,
    }) as span:
        try:
            yield
        except DownloadFailed as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


def _place(src: str | None, dest: str, role: str, t: Target) -> Written:
    """Copy a work file into the book's folder (a copy: the bundle stays
    until the download is done, in case a later step fails)."""
    if not src:
        return []
    try:
        shutil.copyfile(src, dest)
    except OSError as e:
        log.warning("download %s: saving %s failed (non-fatal): %s", t.download_id, role, e)
        return []
    return [(role, dest)]


def _work_file(work_dir: str, download_id: str, suffix: str) -> str:
    return os.path.join(work_dir, f"{download_id}.{suffix}")


def _existing(path: str) -> str | None:
    return path if os.path.isfile(path) else None


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _write_json(path: str, data: dict[str, Any]) -> None:
    """Write via a temporary file and rename, so a reader never sees half a file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


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
