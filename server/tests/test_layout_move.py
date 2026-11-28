"""Moving downloaded books to another layout, on real folders (and the awkward books in tests/fixtures)."""

import json
import os

import pytest

from app.audible_api.models import Series
from app.config import NamingPreset
from app.jobs.filename import FilenameData, book_directory, book_file_name
from app.naming import sanitize_filename
from app.services import layout_move
from app.services.layout_move import LibraryMoveService, MoveInProgress, Outcome, judge, prune_empty
from tests.conftest import add_account, import_books, make_book
from tests.test_naming_fixtures import WITH_ID, names

ASIN = "B0TESTASIN"


def touch(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("x")
    return path


def book_row(root: str, folder: str = f"Title [{ASIN}]", file: str = f"Title [{ASIN}].m4b") -> dict:
    return {"audible_id": ASIN, "file_path": touch(os.path.join(root, folder, file))}


# --- judge: what can safely happen to one folder ------------------------------------------


def decide(book, new_dir, root, others=(), downloading=False):
    return judge(book, new_dir, root, set(others), downloading)


def test_a_book_in_its_own_id_named_folder_moves(tmp_path):
    root = str(tmp_path)
    assert decide(book_row(root), os.path.join(root, "A", f"Title [{ASIN}]"), root) == Outcome.MOVE


def test_a_book_already_in_place_is_left_alone(tmp_path):
    root = str(tmp_path)
    book = book_row(root)
    assert decide(book, os.path.dirname(book["file_path"]), root) == Outcome.IN_PLACE


def test_an_older_folder_with_only_this_book_moves(tmp_path):
    """v0.2.0 named the folder "Author - Title" and the audio file after the title, with no ID."""
    root = str(tmp_path)
    book = book_row(root, "Jane - Title", "Title.m4b")
    touch(os.path.join(root, "Jane - Title", "Title.pdf"))
    touch(os.path.join(root, "Jane - Title", "Title.cue"))
    touch(os.path.join(root, "Jane - Title", "Title - 01 - Intro.m4b"))  # a chapter file of this book
    touch(os.path.join(root, "Jane - Title", "cover.jpg"))
    assert decide(book, os.path.join(root, "Jane", f"Title [{ASIN}]"), root) == Outcome.MOVE


@pytest.mark.parametrize("extra", ["Other.m4b", "Other.mp3", os.path.join("Disc 2", "Part.mp3")])
def test_an_older_folder_with_other_audio_is_not_touched(tmp_path, extra):
    root = str(tmp_path)
    book = book_row(root, "Shelf", "Title.m4b")
    touch(os.path.join(root, "Shelf", extra))
    assert decide(book, os.path.join(root, "New"), root) == Outcome.SHARED_FOLDER


def test_an_older_folder_that_holds_another_books_file_is_not_touched(tmp_path):
    root = str(tmp_path)
    book = book_row(root, "Shelf", "Title.m4b")
    other = os.path.join(root, "Shelf", "Deeper", "Other.txt")  # recorded as another book's file
    assert decide(book, os.path.join(root, "New"), root, others=[other]) == Outcome.SHARED_FOLDER


def test_loose_files_in_the_output_folder_are_not_in_a_folder_of_their_own(tmp_path):
    root = str(tmp_path)
    book = {"audible_id": ASIN, "file_path": touch(os.path.join(root, f"Title [{ASIN}].m4b"))}
    assert decide(book, os.path.join(root, "New"), root) == Outcome.NOT_IN_OWN_FOLDER


def test_a_folder_outside_the_output_folder_is_not_touched(tmp_path):
    root = str(tmp_path / "audiobooks")
    os.makedirs(root)
    outside = book_row(str(tmp_path / "elsewhere"))
    assert decide(outside, os.path.join(root, "New"), root) == Outcome.NOT_IN_OWN_FOLDER


def test_a_symlinked_folder_is_not_touched(tmp_path):
    root = str(tmp_path / "audiobooks")
    real = book_row(str(tmp_path / "real"))
    os.makedirs(root)
    os.symlink(os.path.dirname(real["file_path"]), os.path.join(root, f"Title [{ASIN}]"))
    linked = {"audible_id": ASIN, "file_path": os.path.join(root, f"Title [{ASIN}]", f"Title [{ASIN}].m4b")}
    assert decide(linked, os.path.join(root, "New"), root) == Outcome.NOT_IN_OWN_FOLDER


def test_nothing_is_overwritten_and_nothing_moves_while_downloading(tmp_path):
    root = str(tmp_path)
    book = book_row(root)
    taken = os.path.join(root, "A", f"Title [{ASIN}]")
    os.makedirs(taken)
    assert decide(book, taken, root) == Outcome.TARGET_EXISTS
    assert decide(book, os.path.join(root, "B"), root, downloading=True) == Outcome.DOWNLOADING
    assert decide({**book, "file_path": book["file_path"] + ".gone"}, "x", root) == Outcome.FILE_MISSING


def test_a_folder_cannot_move_into_itself(tmp_path):
    root = str(tmp_path)
    book = book_row(root, "Jane", "Title.m4b")  # the author folder holds just this book
    assert decide(book, os.path.join(root, "Jane", f"Title [{ASIN}]"), root) == Outcome.NESTED


def test_prune_empty_stops_at_the_root_and_at_anything_left(tmp_path):
    root = str(tmp_path)
    touch(os.path.join(root, "a", "keep.txt"))
    os.makedirs(os.path.join(root, "a", "b", "c"))
    prune_empty(os.path.join(root, "a", "b", "c"), root)
    assert sorted(os.listdir(os.path.join(root, "a"))) == ["keep.txt"]
    prune_empty(root, root)
    assert os.path.isdir(root)


# --- the service, on the awkward books ------------------------------------------------------


@pytest.fixture
def mover(db, config, library_svc):
    os.makedirs(config.output_dir)
    return LibraryMoveService(db, config, library_svc)


def audible_book(book: dict):
    series = [Series(asin=f"S-{book['series_name']}", title=book["series_name"], sequence=book["series_index"])] if book["series_name"] else []
    return make_book(book["asin"], title=book["title"], authors=[book["author"]] if book["author"] else [],
                     series=series, release_date=f"{book['year']}-06-01" if book["year"] else None)


def download_all(db, config, library_svc, books: list[dict]) -> dict[str, str]:
    """Each book downloaded the way an old version of Libera left it: a folder named "<title> [<id>]"."""
    add_account(db)
    import_books(db, 1, [audible_book(b) for b in books])
    ids = {r["audible_id"]: r["id"] for r in db.query("SELECT id, audible_id FROM books")}
    paths = {}
    for b in books:
        old = FilenameData(title=b["title"], asin=b["asin"])
        folder = book_directory(config.output_dir, NamingPreset.TITLE, old)
        stem = book_file_name(old)
        paths[b["asin"]] = touch(os.path.join(folder, f"{stem}.m4b"))
        touch(os.path.join(folder, "cover.jpg"))
        touch(os.path.join(folder, f"{stem}.pdf"))
        library_svc.mark_downloaded(ids[b["asin"]], "m4b", paths[b["asin"]])
    return paths


def listing(root: str) -> list[str]:
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, files in os.walk(root) for f in files)


def saved_paths(db) -> dict[str, str]:
    return {r["audible_id"]: r["file_path"] for r in db.query(
        "SELECT b.audible_id, lb.file_path FROM library_books lb JOIN books b ON b.id = lb.book_id")}


def test_every_awkward_book_moves_to_every_layout_and_back(mover, db, config, library_svc):
    download_all(db, config, library_svc, WITH_ID)
    start = listing(config.output_dir)
    for layout in NamingPreset:
        preview = mover.preview(layout)
        result = mover.move(layout)
        assert result["moved"] == preview["to_move"] and result["skipped_total"] == 0
        assert mover.preview(layout)["to_move"] == 0 and mover.preview(layout)["in_place"] == len(WITH_ID)
        files = listing(config.output_dir)
        assert len(files) == len(WITH_ID) * 3, "nothing lost, nothing overwritten"
        assert all(os.path.isfile(p) for p in saved_paths(db).values()), layout
    mover.move(NamingPreset.TITLE)
    assert listing(config.output_dir) == start
    assert sorted(os.listdir(config.output_dir)) == sorted(d for d in os.listdir(config.output_dir) if d.endswith("]")), \
        "no empty author or series folders left behind"


def test_a_book_lands_where_a_new_download_would(mover, db, config, library_svc):
    download_all(db, config, library_svc, WITH_ID)
    mover.move(NamingPreset.AUTHOR_SERIES)
    fellowship = saved_paths(db)["B007978NPG"]
    assert os.path.relpath(fellowship, config.output_dir) == os.path.join(
        "J.R.R. Tolkien", "The Lord of the Rings", "01 - The Fellowship of the Ring [B007978NPG]",
        "The Fellowship of the Ring [B007978NPG].m4b")


def test_unsafe_books_are_reported_and_left_alone(mover, db, config, library_svc):
    add_account(db)
    import_books(db, 1, [make_book("A1", title="Loose"), make_book("A2", title="Shared"), make_book("A3", title="Neighbour")])
    ids = {r["audible_id"]: r["id"] for r in db.query("SELECT id, audible_id FROM books")}
    loose = touch(os.path.join(config.output_dir, "Loose.m4b"))
    shared = touch(os.path.join(config.output_dir, "Shelf", "Shared.m4b"))
    neighbour = touch(os.path.join(config.output_dir, "Shelf", "Neighbour.m4b"))
    for asin, path in (("A1", loose), ("A2", shared), ("A3", neighbour)):
        library_svc.mark_downloaded(ids[asin], "m4b", path)
    result = mover.move(NamingPreset.AUTHOR_FOLDER)
    assert result["moved"] == 0 and result["skipped_total"] == 3
    assert {s["reason"] for s in result["skipped"]} == {layout_move.REASONS[Outcome.NOT_IN_OWN_FOLDER],
                                                       layout_move.REASONS[Outcome.SHARED_FOLDER]}
    assert all(os.path.isfile(p) for p in (loose, shared, neighbour))


def test_an_existing_folder_is_never_overwritten(mover, db, config, library_svc):
    paths = download_all(db, config, library_svc, WITH_ID[:1])
    names_ = names(WITH_ID[0])
    taken = touch(os.path.join(book_directory(config.output_dir, NamingPreset.AUTHOR_FOLDER, names_), "other.txt"))
    result = mover.move(NamingPreset.AUTHOR_FOLDER)
    assert result["moved"] == 0 and result["skipped"][0]["reason"] == layout_move.REASONS[Outcome.TARGET_EXISTS]
    assert os.path.isfile(paths[WITH_ID[0]["asin"]]) and os.path.isfile(taken)


def test_a_failed_save_puts_the_folder_back(mover, db, config, library_svc, monkeypatch):
    paths = download_all(db, config, library_svc, WITH_ID[:2])

    def broken(plan):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(mover, "_remember", broken)
    result = mover.move(NamingPreset.AUTHOR_FOLDER)
    assert result["moved"] == 0
    assert all(os.path.isfile(p) for p in paths.values())
    assert sorted(os.listdir(config.output_dir)) == sorted(os.path.basename(os.path.dirname(p)) for p in paths.values())


def test_a_book_cut_off_by_a_crash_is_found_again_by_find_downloaded_files(mover, db, config, library_svc,
                                                                           monkeypatch):
    """The process dies after a book's folder was renamed but before its new path was saved."""
    paths = download_all(db, config, library_svc, WITH_ID[:2])
    first = WITH_ID[0]["asin"]
    old_folder = os.path.dirname(paths[first])
    db.execute("INSERT INTO downloads (id, library_book_id, format, status, path, base_name) "
               "SELECT 'd1', lb.id, 'm4b', 'done', ?, 'x' FROM library_books lb JOIN books b ON b.id = lb.book_id "
               "WHERE b.audible_id = ?", (old_folder, first))

    class Killed(BaseException):  # like SIGKILL: no cleanup runs
        pass

    def die(plan, renames):
        raise Killed

    monkeypatch.setattr(mover, "_remember", die)
    with pytest.raises(Killed):
        mover.move(NamingPreset.AUTHOR_FOLDER)
    monkeypatch.undo()

    assert not os.path.exists(saved_paths(db)[first]), "stuck: the book points at a folder that is gone"
    assert mover.preview(NamingPreset.AUTHOR_FOLDER)["skipped"][0]["reason"] == layout_move.REASONS[Outcome.FILE_MISSING]

    assert library_svc.rescan() == (0, 1)
    found = saved_paths(db)[first]
    assert os.path.isfile(found) and os.path.dirname(found) == book_directory(
        config.output_dir, NamingPreset.AUTHOR_FOLDER, names(WITH_ID[0]))
    assert db.scalar("SELECT path FROM downloads WHERE id = 'd1'") == os.path.dirname(found)
    preview = mover.preview(NamingPreset.AUTHOR_FOLDER)
    assert preview["skipped_total"] == 0 and preview["in_place"] == 1 and preview["to_move"] == 1
    assert mover.move(NamingPreset.AUTHOR_FOLDER)["moved"] == 1


def test_only_one_move_runs_at_a_time(mover):
    mover._busy.acquire()
    with pytest.raises(MoveInProgress):
        mover.move(NamingPreset.AUTHOR_FOLDER)


def test_preview_changes_nothing_and_shows_examples(mover, db, config, library_svc):
    download_all(db, config, library_svc, WITH_ID[:5])
    before = listing(config.output_dir)
    preview = mover.preview(NamingPreset.AUTHOR_FOLDER)
    assert listing(config.output_dir) == before
    assert preview["to_move"] == 5 and len(preview["examples"]) == layout_move.EXAMPLE_COUNT
    assert preview["examples"][0] == {"from": "The Fellowship of the Ring [B007978NPG]",
                                      "to": os.path.join("J.R.R. Tolkien", "The Fellowship of the Ring [B007978NPG]")}


# --- books downloaded by v0.2.0, which named the audio file after the title with no ID -------


def download_as_v020(db, config, library_svc, books: list[dict]) -> None:
    """v0.2.0's layout: "Author - Title/" holding "Title.m4b", sidecars named after the title, and chapter files."""
    add_account(db)
    import_books(db, 1, [audible_book(b) for b in books])
    ids = {r["audible_id"]: r["id"] for r in db.query("SELECT id, audible_id FROM books")}
    for b in books:
        stem = sanitize_filename(b["title"])
        folder = os.path.join(config.output_dir, sanitize_filename(f"{b['author']} - {b['title']}"))
        audio = touch(os.path.join(folder, f"{stem}.m4b"))
        for name in ("cover.jpg", f"{stem}.pdf", f"{stem}.cue", f"{stem}.chapters.json", f"{stem} - 01 - Intro.m4b"):
            touch(os.path.join(folder, name))
        library_svc.mark_downloaded(ids[b["asin"]], "m4b", audio)


# Two books with the same author and title shared a folder name even in v0.2.0, so they are left out.
V020_BOOKS = [b for b in WITH_ID if b["title"] and b["author"] and b["title"] != "The Hobbit"
              and sanitize_filename(b["title"]) != "audiobook"]


@pytest.mark.parametrize("layout", NamingPreset)
def test_older_books_move_and_get_their_id_in_every_file_name(mover, db, config, library_svc, layout):
    download_as_v020(db, config, library_svc, V020_BOOKS)
    preview = mover.preview(layout)
    assert preview["to_move"] == len(V020_BOOKS) and preview["to_rename"] == len(V020_BOOKS)
    assert preview["skipped_total"] == 0
    result = mover.move(layout)
    assert result["moved"] == len(V020_BOOKS) and result["skipped_total"] == 0
    assert len(listing(config.output_dir)) == len(V020_BOOKS) * 6, "nothing lost, nothing overwritten"
    for asin, path in saved_paths(db).items():
        folder = os.path.dirname(path)
        assert os.path.isfile(path) and f"[{asin}]" in os.path.basename(path)
        siblings = sorted(os.listdir(folder))
        assert len([n for n in siblings if n.endswith(".m4b")]) == 2 and "cover.jpg" in siblings
        assert all(f"[{asin}]" in n for n in siblings if n != "cover.jpg"), siblings
    assert not any(" - " in d and d.startswith(("Jane Author - ", "J.R.R. Tolkien - ")) for d in os.listdir(config.output_dir))
    assert mover.preview(layout)["to_move"] == 0


def test_an_older_books_downloads_follow_the_rename(mover, db, config, library_svc):
    download_as_v020(db, config, library_svc, V020_BOOKS[:1])
    book = V020_BOOKS[0]
    folder = os.path.join(config.output_dir, sanitize_filename(f"{book['author']} - {book['title']}"))
    db.execute("INSERT INTO downloads (id, library_book_id, format, status, path, base_name, files) VALUES "
               "('d1', 1, 'm4b', 'done', ?, ?, ?)",
               (folder, sanitize_filename(book["title"]),
                json.dumps([{"role": "audio", "name": sanitize_filename(book["title"]) + ".m4b", "size_bytes": 1}])))
    mover.move(NamingPreset.AUTHOR_FOLDER)
    row = db.query("SELECT path, base_name, files FROM downloads WHERE id = 'd1'")[0]
    assert row["path"] == os.path.dirname(saved_paths(db)[book["asin"]])
    assert row["base_name"].endswith(f"[{book['asin']}]")
    assert json.loads(row["files"])[0]["name"] == os.path.basename(saved_paths(db)[book["asin"]])


# --- the API --------------------------------------------------------------------------------


def test_the_api_previews_and_moves(client, db, config, library_svc):
    download_all(db, config, library_svc, WITH_ID[:3])
    preview = client.get("/api/library/move-preview", params={"naming": "author_folder"}).json()
    assert preview["to_move"] == 3 and preview["skipped_total"] == 0
    moved = client.post("/api/library/move", json={"naming": "author_folder"}).json()
    assert moved["moved"] == 3
    assert client.get("/api/library/move-preview", params={"naming": "author_folder"}).json()["to_move"] == 0


def test_the_api_rejects_an_unknown_layout(client):
    assert client.get("/api/library/move-preview", params={"naming": "nope"}).status_code == 422
    assert client.post("/api/library/move", json={"naming": "nope"}).status_code == 422
