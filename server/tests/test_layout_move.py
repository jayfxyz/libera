"""Moving downloaded books to another layout, on real folders (and the awkward books in tests/fixtures)."""

import os

import pytest

from app.audible_api.models import Series
from app.config import NamingPreset
from app.jobs.filename import FilenameData, book_directory, book_file_name
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


def test_a_book_in_its_own_id_named_folder_moves(tmp_path):
    root = str(tmp_path)
    assert judge(book_row(root), os.path.join(root, "A", f"Title [{ASIN}]"), root, downloading=False) == Outcome.MOVE


def test_a_book_already_in_place_is_left_alone(tmp_path):
    root = str(tmp_path)
    book = book_row(root)
    assert judge(book, os.path.dirname(book["file_path"]), root, downloading=False) == Outcome.IN_PLACE


@pytest.mark.parametrize("folder, file, outcome", [
    ("Title", "Title.m4b", Outcome.NO_ID_IN_NAME),  # before Libera named things with the ID
    (f"Title [{ASIN}]", "Title.m4b", Outcome.NO_ID_IN_NAME),
    (f"Title [OTHER]", f"Title [{ASIN}].m4b", Outcome.NO_ID_IN_NAME),  # another book's folder
])
def test_names_without_the_books_own_id_are_not_touched(tmp_path, folder, file, outcome):
    root = str(tmp_path)
    assert judge(book_row(root, folder, file), os.path.join(root, "New"), root, downloading=False) == outcome


def test_loose_files_in_the_output_folder_are_not_in_a_folder_of_their_own(tmp_path):
    root = str(tmp_path)
    book = {"audible_id": ASIN, "file_path": touch(os.path.join(root, f"Title [{ASIN}].m4b"))}
    assert judge(book, os.path.join(root, "New"), root, downloading=False) == Outcome.NOT_IN_OWN_FOLDER


def test_a_folder_outside_the_output_folder_is_not_touched(tmp_path):
    root = str(tmp_path / "audiobooks")
    os.makedirs(root)
    outside = book_row(str(tmp_path / "elsewhere"))
    assert judge(outside, os.path.join(root, "New"), root, downloading=False) == Outcome.NOT_IN_OWN_FOLDER


def test_a_symlinked_folder_is_not_touched(tmp_path):
    root = str(tmp_path / "audiobooks")
    real = book_row(str(tmp_path / "real"))
    os.makedirs(root)
    os.symlink(os.path.dirname(real["file_path"]), os.path.join(root, f"Title [{ASIN}]"))
    linked = {"audible_id": ASIN, "file_path": os.path.join(root, f"Title [{ASIN}]", f"Title [{ASIN}].m4b")}
    assert judge(linked, os.path.join(root, "New"), root, downloading=False) == Outcome.NOT_IN_OWN_FOLDER


def test_nothing_is_overwritten_and_nothing_moves_while_downloading(tmp_path):
    root = str(tmp_path)
    book = book_row(root)
    taken = os.path.join(root, "A", f"Title [{ASIN}]")
    os.makedirs(taken)
    assert judge(book, taken, root, downloading=False) == Outcome.TARGET_EXISTS
    assert judge(book, os.path.join(root, "B"), root, downloading=True) == Outcome.DOWNLOADING
    assert judge({**book, "file_path": book["file_path"] + ".gone"}, "x", root, downloading=False) == Outcome.FILE_MISSING


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


def test_old_names_without_an_id_are_reported_and_left_alone(mover, db, config, library_svc):
    add_account(db)
    import_books(db, 1, [make_book("A1", title="Loose"), make_book("A2", title="Old folder")])
    ids = {r["audible_id"]: r["id"] for r in db.query("SELECT id, audible_id FROM books")}
    loose = touch(os.path.join(config.output_dir, "Loose.m4b"))
    old = touch(os.path.join(config.output_dir, "Old folder", "Old folder.m4b"))
    library_svc.mark_downloaded(ids["A1"], "m4b", loose)
    library_svc.mark_downloaded(ids["A2"], "m4b", old)
    result = mover.move(NamingPreset.AUTHOR_FOLDER)
    assert result["moved"] == 0 and result["skipped_total"] == 2
    assert {s["reason"] for s in result["skipped"]} == {layout_move.REASONS[Outcome.NOT_IN_OWN_FOLDER],
                                                       layout_move.REASONS[Outcome.NO_ID_IN_NAME]}
    assert os.path.isfile(loose) and os.path.isfile(old)


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
