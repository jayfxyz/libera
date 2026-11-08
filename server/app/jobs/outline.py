"""Audible's chapter outline: flattening, ffmpeg metadata, .cue and .chapters.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

# Joins a part's title to its chapters': "Part One: Chapter 1" (as Libation does).
NESTED_TITLE_SEP = ": "
# A part heading shorter than this is just the narrator reading the title, so
# it's folded into its first chapter instead of kept as a chapter (Libation's rule).
SHORT_PARENT_MS = 10_000


@dataclass
class OutlineChapter:
    title: str
    start_ms: int
    end_ms: int


def flatten_chapters(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten Audible's chapter tree, prefixing children with their parents' titles.

    The input is not modified.
    """
    out: list[dict[str, Any]] = []
    for c in chapters:
        node = {"title": c.get("title", ""), "start_offset_ms": c.get("start_offset_ms", 0),
                "length_ms": c.get("length_ms", 0)}
        children = c.get("chapters") or []
        if not children:
            out.append(node)
            continue
        flat_children = flatten_chapters(children)
        if node["length_ms"] < SHORT_PARENT_MS:
            flat_children[0]["start_offset_ms"] = node["start_offset_ms"]
            flat_children[0]["length_ms"] += node["length_ms"]
        else:
            out.append(node)
        for child in flat_children:
            child["title"] = node["title"] + NESTED_TITLE_SEP + child["title"]
        out.extend(flat_children)
    return out


def build_outline(info: dict[str, Any] | None) -> list[OutlineChapter]:
    """Contiguous chapters: each ends where the next starts, the last at the
    book's runtime. Chapters left with no duration are dropped."""
    if not info:
        return []
    flat = sorted(flatten_chapters(info.get("chapters") or []), key=lambda c: c["start_offset_ms"])
    runtime = info.get("runtime_length_ms") or 0
    out = []
    for i, c in enumerate(flat):
        start = c["start_offset_ms"]
        end = start + c["length_ms"]
        if i + 1 < len(flat):
            end = flat[i + 1]["start_offset_ms"]
        elif runtime > end:
            end = runtime
        if end > start:
            out.append(OutlineChapter(c["title"].strip(), start, end))
    return out


def _escape_ffmetadata(s: str) -> str:
    for ch in ("\\", "=", ";", "#", "\n"):
        s = s.replace(ch, "\\" + ch)
    return s


def ffmetadata(chapters: list[OutlineChapter]) -> str:
    """Chapters in ffmpeg's FFMETADATA1 format, for -map_chapters."""
    parts = [";FFMETADATA1\n"]
    for c in chapters:
        parts.append(
            f"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={c.start_ms}\nEND={c.end_ms}\n"
            f"title={_escape_ffmetadata(c.title)}\n"
        )
    return "".join(parts)


def cue_sheet(audio_file_name: str, chapters: list[OutlineChapter]) -> str:
    """Cue sheet pointing at the audio file. Positions are mm:ss:ff, in frames
    of 1/75 s. The file type is always MP3, as Libation writes it: the format
    has no MP4 type and players that read cue sheets accept it."""
    lines = [f'FILE "{audio_file_name.replace(chr(34), chr(39))}" MP3']
    for i, c in enumerate(chapters, 1):
        minutes, rest = divmod(c.start_ms, 60_000)
        seconds, ms = divmod(rest, 1000)
        frames = ms * 75 // 1000
        lines += [
            f"TRACK {i} AUDIO",
            f'  TITLE "{c.title.replace(chr(34), chr(39))}"',
            f"  INDEX 01 {minutes:02d}:{seconds:02d}:{frames:02d}",
        ]
    return "\n".join(lines) + "\n"


def write_outline_files(audio_file: str, asin: str, title: str, info: dict[str, Any],
                        chapters: list[OutlineChapter]) -> None:
    """Write <audio>.cue and <audio>.chapters.json next to the audio file."""
    base, _ = os.path.splitext(audio_file)
    name = os.path.basename(audio_file)
    with open(base + ".cue", "w", encoding="utf-8") as f:
        f.write(cue_sheet(name, chapters))
    doc = {
        "asin": asin,
        "title": title,
        "audio_file": name,
        "runtime_ms": info.get("runtime_length_ms") or 0,
        "chapters": [asdict(c) for c in chapters],
        "audible_chapter_info": info,
    }
    with open(base + ".chapters.json", "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
