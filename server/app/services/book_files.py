"""The files a downloaded book has on disk, for the book panel."""

from __future__ import annotations

import os
from enum import StrEnum
from pydantic import BaseModel

from ..naming import AUDIO_EXTENSIONS, belongs_to_book, named_with_id

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class FileKind(StrEnum):
    AUDIO = "audio"
    COVER = "cover"
    PDF = "pdf"
    OTHER = "other"


class BookFile(BaseModel):
    name: str
    size_bytes: int
    kind: FileKind


class BookFiles(BaseModel):
    root: str  # the output folder (or, for a book outside it, the folder above the book's)
    folders: list[str]  # from root down to the book's own folder
    files: list[BookFile]
    found: bool  # False when the book is not on disk; the one file listed is then where it is expected


def file_kind(name: str) -> FileKind:
    extension = os.path.splitext(name)[1].lower()
    if extension in (*AUDIO_EXTENSIONS, ".m4a"):
        return FileKind.AUDIO
    if extension in IMAGE_EXTENSIONS:
        return FileKind.COVER
    return FileKind.PDF if extension == ".pdf" else FileKind.OTHER


def list_book_files(output_dir: str, file_path: str | None, asin: str, expected_path: str | None = None) -> BookFiles:
    """Where the book's files are (folders under root) and which, with sizes. found is False when there are none;
    the one file listed is then where the book is expected to be, with a size of 0.

    A folder named with the book's ID holds only this book, so all of it is listed. In any other folder (one you
    arranged yourself) only the audio file and the files named after it are, since the rest may be other books'."""
    output_dir = os.path.abspath(output_dir)
    if not file_path or not os.path.isfile(file_path):
        return _expected(output_dir, file_path or expected_path)
    file_path = os.path.abspath(file_path)
    folder = os.path.dirname(file_path)
    root, folders = _location(output_dir, folder)
    names = _names_to_list(folder, file_path, asin)
    files = [BookFile(name=n, size_bytes=os.path.getsize(os.path.join(folder, n)), kind=file_kind(n)) for n in names]
    return BookFiles(root=root, folders=folders, files=files, found=True)


def _expected(output_dir: str, path: str | None) -> BookFiles:
    """Where a book that is not on disk is, or would be saved: one file, in its folders."""
    if not path:
        return BookFiles(root=output_dir, folders=[], files=[], found=False)
    path = os.path.abspath(path)
    root, folders = _location(output_dir, os.path.dirname(path))
    name = os.path.basename(path)
    return BookFiles(root=root, folders=folders, files=[BookFile(name=name, size_bytes=0, kind=file_kind(name))],
                     found=False)


def _location(output_dir: str, folder: str) -> tuple[str, list[str]]:
    """(root, folders from root to the book's folder). Outside the output folder, the folder hangs off its parent."""
    if folder != output_dir and os.path.commonpath([output_dir, folder]) == output_dir:
        return output_dir, os.path.relpath(folder, output_dir).split(os.sep)
    return os.path.dirname(folder), [os.path.basename(folder)]


def _names_to_list(folder: str, file_path: str, asin: str) -> list[str]:
    everything = sorted(n for n in os.listdir(folder) if not n.startswith(".") and os.path.isfile(os.path.join(folder, n)))
    if not named_with_id(asin, file_path):
        stem = os.path.splitext(os.path.basename(file_path))[0]
        everything = [n for n in everything if n == os.path.basename(file_path) or belongs_to_book(n, stem)]
    main = os.path.basename(file_path)
    return sorted(everything, key=lambda n: (n != main, file_kind(n) != FileKind.AUDIO, n.lower()))
