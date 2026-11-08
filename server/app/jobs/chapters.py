"""Split a decrypted book into one file per chapter."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from ..library import sanitize_filename
from .ffmpeg import chapter_args
from .process import run

log = logging.getLogger(__name__)


@dataclass
class ProbedChapter:
    id: int
    title: str
    start_sec: float
    end_sec: float


def parse_chapters(ffprobe_json: str | bytes) -> list[ProbedChapter]:
    """Chapters from `ffprobe -show_chapters -of json` output. Raises ValueError on bad JSON."""
    raw = json.loads(ffprobe_json)
    return [
        ProbedChapter(
            id=c.get("id", i),
            title=(c.get("tags") or {}).get("title", ""),
            start_sec=float(c.get("start_time") or 0),
            end_sec=float(c.get("end_time") or 0),
        )
        for i, c in enumerate(raw.get("chapters") or [])
    ]


def chapter_path(directory: str, book_base: str, n: int, title: str) -> str:
    chapter_title = sanitize_filename(title)
    if not title.strip() or chapter_title == "audiobook":
        chapter_title = f"Chapter_{n + 1:02d}"
    return os.path.join(directory, sanitize_filename(f"{book_base} - {n + 1:02d} - {chapter_title}"))


async def split_into_chapters(audio_file: str, directory: str, book_base: str, ext: str) -> int:
    """Write one file per chapter embedded in audio_file. Returns files written.

    Individual chapter failures are logged and skipped.
    """
    code, out, err = await run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", audio_file])
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {err.decode(errors='replace').strip()}")
    written = 0
    for i, ch in enumerate(parse_chapters(out)):
        dest = chapter_path(directory, book_base, i, ch.title) + ext
        code, _, err = await run(chapter_args(audio_file, dest, ch.start_sec, ch.end_sec))
        if code == 0:
            written += 1
        else:
            log.warning("chapter %d extract failed: %s", i, err.decode(errors="replace").strip()[-500:])
    return written
