"""Where a book's files go: a folder (or nested folders) chosen by a NamingPreset, and the audio file's name.

The folder holding a book's files and the audio file are always named "<title> [<asin>]" (the Libation and
Audiobookshelf convention), so two books with the same title never share a name."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..config import NamingPreset
from ..naming import clean_name, sanitize_filename

_EMPTY = "\x00"
# An empty tag, together with a separator right before or after it.
_EMPTY_WITH_SEPARATOR = re.compile(r"\s*[-_,]\s*\x00|\x00\s*[-_,]\s*|\x00")

# Each preset is a list of folder names, outermost first. A folder whose tags are all empty is left out,
# so a book with no series goes in Author/Title and one with no author in Title.
_FOLDERS: dict[NamingPreset, tuple[str, ...]] = {
    NamingPreset.TITLE: ("{title}",),
    NamingPreset.AUTHOR_FOLDER: ("{author}", "{title}"),
    NamingPreset.AUTHOR_FOLDER_YEAR: ("{author}", "{year} - {title}"),
    NamingPreset.AUTHOR_SERIES: ("{author}", "{series}", "{series_index} - {title}"),
    NamingPreset.AUTHOR_SERIES_YEAR: ("{author}", "{series}", "{series_index} - {year} - {title}"),
}


@dataclass
class FilenameData:
    title: str = ""
    author: str = ""  # the first author only
    series_name: str = ""
    series_index: str = ""
    year: str = ""
    asin: str = ""


def asin_suffix(data: FilenameData) -> str:
    """" [B0123456789]", or "" for a book without an ASIN."""
    asin = clean_name(data.asin)
    return f" [{asin}]" if asin else ""


def book_file_name(data: FilenameData) -> str:
    """The audio file's name without its extension: the title and the ASIN."""
    suffix = asin_suffix(data)
    return sanitize_filename(data.title, reserve=len(suffix.encode())) + suffix


def book_directory(output_dir: str, naming: NamingPreset, data: FilenameData) -> str:
    """The folder a book's files go in, inside output_dir. The innermost folder ends with the ASIN."""
    folders = [fill(template=template, data=data) for template in _FOLDERS[naming][:-1]]
    suffix = asin_suffix(data)
    last = fill(template=_FOLDERS[naming][-1], data=data, reserve=len(suffix.encode()))
    return os.path.join(output_dir, *(folder for folder in folders if folder), (last + suffix).strip())


def pad_series_index(index: str) -> str:
    """"2" → "02" and "2.5" → "02.5", so books sort in order ("10" would otherwise sort before "2").
    Audiobookshelf reads "02 - Title" as book 2. Anything that is not a number is left alone."""
    whole, dot, fraction = index.partition(".")
    return f"{whole.zfill(2)}{dot}{fraction}" if whole.isdigit() and (not dot or fraction.isdigit()) else index


def fill(template: str, data: FilenameData, reserve: int = 0) -> str:
    """One folder name: the template's tags filled in, an empty tag dropped with its separator.
    Returns "" when every tag is empty. reserve is how many bytes the caller still adds to the name."""
    tags = {
        "{title}": data.title,
        "{author}": data.author,
        "{series}": data.series_name,
        "{series_index}": pad_series_index(data.series_index),
        "{year}": data.year,
    }
    result = template
    for tag, value in tags.items():
        result = result.replace(tag, clean_name(value) or _EMPTY)
    result = _EMPTY_WITH_SEPARATOR.sub("", result).strip()
    return sanitize_filename(result, reserve=reserve) if result else ""
