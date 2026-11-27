"""Every layout against awkward real-world metadata (tests/fixtures/naming_books.json).

Each book there has a "note" saying what it checks. To cover a new edge case, add a book to the JSON file: every
rule below then applies to it with no other change."""

import json
import os
import re
import unicodedata
from pathlib import Path

import pytest

from app.config import NamingPreset
from app.jobs.chapters import FILE_NAME_LIMIT_BYTES, chapter_path
from app.jobs.filename import FilenameData, book_directory, book_file_name
from app.naming import MAX_NAME_BYTES
from app.services.library import DiskFile, asin_files_on_disk

OUTPUT = "/audiobooks"
ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)


def load_books() -> list[dict]:
    return json.loads((Path(__file__).parent / "fixtures" / "naming_books.json").read_text())


BOOKS = load_books()
WITH_ID = [b for b in BOOKS if b["asin"]]


def names(book: dict) -> FilenameData:
    return FilenameData(**{k: v for k, v in book.items() if k != "note"})


def components(preset: NamingPreset, book: dict) -> list[str]:
    """The folders under the output folder, outermost first."""
    folder = book_directory(OUTPUT, preset, names(book))
    return os.path.relpath(folder, OUTPUT).split(os.sep)


def label(book: dict) -> str:
    return book["note"][:50]


@pytest.mark.parametrize("preset", NamingPreset)
@pytest.mark.parametrize("book", BOOKS, ids=label)
def test_every_name_is_safe_everywhere(preset, book):
    folder = book_directory(OUTPUT, preset, names(book))
    parts = components(preset, book)
    assert os.path.commonpath([OUTPUT, folder]) == OUTPUT, "stays inside the output folder"
    for part in [*parts, book_file_name(names(book))]:
        assert part and part not in (".", ".."), part
        assert not ILLEGAL.search(part), part
        assert part == part.strip(" ."), f"leading or trailing dot or space: {part!r}"
        assert not RESERVED.match(part), f"reserved on Windows: {part!r}"
        assert unicodedata.is_normalized("NFC", part), f"not NFC: {part!r}"
        assert len(part.encode()) <= MAX_NAME_BYTES, part


@pytest.mark.parametrize("preset", NamingPreset)
@pytest.mark.parametrize("book", WITH_ID, ids=label)
def test_the_book_folder_and_file_end_with_the_id(preset, book):
    suffix = f" [{book['asin']}]"
    assert components(preset, book)[-1].endswith(suffix)
    assert book_file_name(names(book)).endswith(suffix)


@pytest.mark.parametrize("preset", NamingPreset)
def test_books_never_share_a_folder(preset):
    folders = [book_directory(OUTPUT, preset, names(b)) for b in WITH_ID]
    assert len(set(folders)) == len(folders)


@pytest.mark.parametrize("preset", NamingPreset)
@pytest.mark.parametrize("book", WITH_ID, ids=label)
def test_rescan_finds_the_book_again_by_its_id(preset, book):
    stem = book_file_name(names(book))
    path = os.path.join(book_directory(OUTPUT, preset, names(book)), stem + ".m4b")
    found = asin_files_on_disk({stem: DiskFile(format="m4b", path=path)})
    assert found == {book["asin"]: DiskFile(format="m4b", path=path)}


@pytest.mark.parametrize("book", WITH_ID, ids=label)
def test_chapter_files_fit_the_filesystem_limit(book):
    base = book_file_name(names(book))
    for title in ("", "Chapter One", "章" * 200, "x" * 400):
        name = os.path.basename(chapter_path("/d", base, 11, title)) + ".m4b.part"
        assert len(name.encode()) <= FILE_NAME_LIMIT_BYTES, title[:10]
        assert f" - 12 - " in name and base in name, "the book name and number are kept whole"


@pytest.mark.parametrize("preset", [NamingPreset.AUTHOR_SERIES, NamingPreset.AUTHOR_SERIES_YEAR])
def test_a_series_sorts_in_reading_order(preset):
    series = [b for b in BOOKS if b["author"] == "Patrick Rothfuss" and b["series_name"]]
    by_name = sorted(series, key=lambda b: components(preset, b)[-1])
    assert [b["series_index"] for b in by_name] == ["2.5", "10"]
    tolkien = [b for b in BOOKS if b["series_name"] == "The Lord of the Rings"]
    assert [b["series_index"] for b in sorted(tolkien, key=lambda b: components(preset, b)[-1])] == ["1", "2"]


def test_a_few_names_in_full():
    by_note = {b["note"]: b for b in BOOKS}
    cases = {
        "Colon in a title becomes ' - '": (NamingPreset.AUTHOR_FOLDER, "Frank Herbert/Dune - Part One [B09COLON001]"),
        "Slash in both title and author must not nest folders": (NamingPreset.AUTHOR_FOLDER, "AC_DC/AC_DC - The Story [B00SLASH001]"),
        "Trailing dots are stripped (Windows rejects them)": (NamingPreset.AUTHOR_FOLDER, "Jane Author/Wait for it [B00DOTS0001]"),
        "No author: the author folder is left out": (NamingPreset.AUTHOR_FOLDER, "Anonymous Tales [B00NOAUTHOR]"),
        "Decimal series number (a novella between books)": (NamingPreset.AUTHOR_SERIES, "Patrick Rothfuss/Kingkiller Chronicle/02.5 - The Wise Man's Fear Interlude [B00NOVELLA1]"),
        "Standalone: no series folder": (NamingPreset.AUTHOR_SERIES_YEAR, "Susanna Clarke/2020 - Piranesi [B08FYH2QK2]"),
        "No title at all": (NamingPreset.TITLE, "audiobook [B00NOTITLE1]"),
    }
    for note, (preset, expected) in cases.items():
        assert "/".join(components(preset, by_note[note])) == expected, note
