"""Filename and folder templates, e.g. "{author} - {title}"."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..services.library import sanitize_filename

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_EMPTY = "\x00"
# An empty tag, together with a separator right before or after it.
_EMPTY_WITH_SEPARATOR = re.compile(r"\s*[-_,/]\s*\x00|\x00\s*[-_,/]\s*|\x00")


@dataclass
class FilenameData:
    title: str = ""
    authors: str = ""  # comma-separated
    narrators: str = ""
    series_name: str = ""
    series_index: str = ""
    year: str = ""
    language: str = ""
    duration_h: str = ""  # whole hours, e.g. "21"


def render_filename(template: str, data: FilenameData) -> str:
    """Fill a template's tags; an empty tag is dropped with its separator.

    Tags: {title} {author} {narrator} {series} {series_index} {year}
    {language} {duration_h}. An empty template means {title}.
    """
    tags = {
        "{title}": data.title,
        "{author}": data.authors,
        "{narrator}": data.narrators,
        "{series}": data.series_name,
        "{series_index}": data.series_index,
        "{year}": data.year,
        "{language}": data.language,
        "{duration_h}": data.duration_h,
    }
    result = template or "{title}"
    for tag, value in tags.items():
        result = result.replace(tag, _UNSAFE.sub("_", value) if value else _EMPTY)
    result = _EMPTY_WITH_SEPARATOR.sub("", result).strip()
    return sanitize_filename(result or _UNSAFE.sub("_", data.title))


def book_directory(output_dir: str, folder_template: str, data: FilenameData) -> str:
    """The folder a book's files go in: a folder named by the template inside
    output_dir, or output_dir itself when the template is blank."""
    if not folder_template.strip():
        return output_dir
    return os.path.join(output_dir, render_filename(folder_template, data))
