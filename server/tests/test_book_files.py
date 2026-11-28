"""The files a downloaded book has on disk, for the book panel."""

import os

import pytest

from app.services.book_files import FileKind, file_kind, list_book_files
from tests.conftest import add_account, import_books, make_book

ASIN = "B0TESTASIN"


def touch(path: str, size: int = 1) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    return path


def names(listing: dict) -> list[str]:
    return [f["name"] for f in listing["files"]]


@pytest.mark.parametrize("name, kind", [
    ("a.m4b", FileKind.AUDIO), ("a.MP3", FileKind.AUDIO), ("a.m4a", FileKind.AUDIO),
    ("cover.jpg", FileKind.COVER), ("a.PNG", FileKind.COVER), ("a.pdf", FileKind.PDF),
    ("a.cue", FileKind.OTHER), ("a.chapters.json", FileKind.OTHER), ("noextension", FileKind.OTHER),
])
def test_file_kinds(name, kind):
    assert file_kind(name) == kind


def test_a_book_folder_named_with_its_id_lists_everything_in_it(tmp_path):
    root = str(tmp_path)
    folder = os.path.join(root, "Jane", f"Title [{ASIN}]")
    audio = touch(os.path.join(folder, f"Title [{ASIN}].m4b"), 500)
    for name in ("cover.jpg", f"Title [{ASIN}].pdf", f"Title [{ASIN}].cue", f"Title [{ASIN}] - 01 - Intro.m4b", ".hidden"):
        touch(os.path.join(folder, name))
    listing = list_book_files(root, audio, ASIN)
    assert listing["found"] and listing["root"] == root and listing["folders"] == ["Jane", f"Title [{ASIN}]"]
    assert names(listing)[0] == f"Title [{ASIN}].m4b", "the audiobook comes first"
    assert sorted(names(listing)) == sorted([f"Title [{ASIN}].m4b", "cover.jpg", f"Title [{ASIN}].pdf", f"Title [{ASIN}].cue",
                                             f"Title [{ASIN}] - 01 - Intro.m4b"])
    assert listing["files"][0] == {"name": f"Title [{ASIN}].m4b", "size_bytes": 500, "kind": FileKind.AUDIO}


def test_a_folder_you_arranged_yourself_lists_only_this_books_files(tmp_path):
    root = str(tmp_path)
    audio = touch(os.path.join(root, "Shelf", "Title.m4b"))
    touch(os.path.join(root, "Shelf", "Title.pdf"))
    touch(os.path.join(root, "Shelf", "Other.m4b"))  # another book's
    touch(os.path.join(root, "Shelf", "cover.jpg"))  # could be anyone's
    assert names(list_book_files(root, audio, ASIN)) == ["Title.m4b", "Title.pdf"]


def test_a_book_with_no_file_on_disk_says_so(tmp_path):
    root = str(tmp_path)
    assert list_book_files(root, None, ASIN)["found"] is False
    assert list_book_files(root, os.path.join(root, "gone.m4b"), ASIN) == {"root": root, "folders": [], "files": [], "found": False}


def test_a_book_outside_the_output_folder_hangs_off_its_parent(tmp_path):
    root = str(tmp_path / "audiobooks")
    os.makedirs(root)
    audio = touch(str(tmp_path / "elsewhere" / "Book" / "Title.m4b"))
    listing = list_book_files(root, audio, ASIN)
    assert listing["root"] == str(tmp_path / "elsewhere") and listing["folders"] == ["Book"]


def test_the_api_lists_a_downloaded_books_files(client, db, config, library_svc):
    add_account(db)
    import_books(db, 1, [make_book(ASIN, title="Title")])
    book_id = db.query("SELECT id FROM books")[0]["id"]
    folder = os.path.join(config.output_dir, f"Title [{ASIN}]")
    audio = touch(os.path.join(folder, f"Title [{ASIN}].m4b"), 42)
    touch(os.path.join(folder, "cover.jpg"))
    library_svc.mark_downloaded(book_id, "m4b", audio)
    got = client.get(f"/api/library/{book_id}/files").json()
    assert got["found"] is True and got["folders"] == [f"Title [{ASIN}]"]
    assert [(f["name"], f["size_bytes"], f["kind"]) for f in got["files"]] == [
        (f"Title [{ASIN}].m4b", 42, "audio"), ("cover.jpg", 1, "cover")]
    assert client.get("/api/library/9999/files").status_code == 404
    assert client.get(f"/api/library/{book_id}/files").status_code == 200


def test_the_api_says_when_a_book_has_no_files(client, db):
    add_account(db)
    import_books(db, 1, [make_book(ASIN)])
    book_id = db.query("SELECT id FROM books")[0]["id"]
    assert client.get(f"/api/library/{book_id}/files").json()["found"] is False
