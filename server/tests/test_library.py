import pytest

from app.services import library
from tests.conftest import add_account, make_book, import_books


def counts(db, account_id):
    rows = db.query("SELECT is_deleted, COUNT(*) AS n FROM library_books WHERE account_id = ? GROUP BY is_deleted",
                    (account_id,))
    by = {r["is_deleted"]: r["n"] for r in rows}
    return by.get(0, 0), by.get(1, 0)  # (active, deleted)


def test_import_marks_missing_books_deleted_and_restores_them(db):
    add_account(db)
    import_books(db, 1, [make_book(a) for a in ("A1", "A2", "A3")])
    assert counts(db, 1) == (3, 0)
    import_books(db, 1, [make_book(a) for a in ("A1", "A3")])
    assert counts(db, 1) == (2, 1)
    import_books(db, 1, [make_book(a) for a in ("A1", "A2", "A3")])
    assert counts(db, 1) == (3, 0)


def test_import_deletion_is_per_account(db):
    add_account(db, 1)
    add_account(db, 2, "amzn1.account.OTHER")
    import_books(db, 1, [make_book("A1"), make_book("A2")])
    import_books(db, 2, [make_book("A1"), make_book("A2")])
    import_books(db, 1, [make_book("A1")])
    assert counts(db, 1) == (1, 1)
    assert counts(db, 2) == (2, 0)


def test_import_empty_scan_marks_all_deleted(db):
    add_account(db)
    import_books(db, 1, [make_book("A1")])
    import_books(db, 1, [])
    assert counts(db, 1) == (0, 1)


def test_import_saves_release_date_and_language(db):
    add_account(db)
    import_books(db, 1, [make_book("A", release_date="2001-05-01")])
    # A rescan without a release date keeps the stored one.
    import_books(db, 1, [make_book("A", language="english")])
    row = db.query_one("SELECT date_published, language FROM books WHERE audible_id = 'A'")
    assert (row["date_published"], row["language"]) == ("2001-05-01", "english")


def test_import_keeps_contributor_order(db, library_svc):
    add_account(db)
    import_books(db, 1, [make_book("A", authors=["Zed", "Amy"], narrators=["Nia"])])
    book_id = db.scalar("SELECT id FROM books WHERE audible_id = 'A'")
    assert library_svc.contributors(book_id) == {"author": ["Zed", "Amy"], "narrator": ["Nia"]}


@pytest.fixture
def sorted_db(db):
    add_account(db)
    import_books(db, 1, [
        make_book("A", title="beta", authors=["Zed"], date_added="2024-03-01", release_date="2001-05-01",
                  runtime_length_min=300, rating=4.1, series=[{"asin": "S1", "title": "Saga", "sequence": "10"}]),
        make_book("B", title="Alpha", authors=["Amy"], date_added="2024-01-01", release_date="2020-01-01",
                  runtime_length_min=900, rating=4.8, series=[{"asin": "S1", "title": "Saga", "sequence": "2"}]),
        # No release date, rating or series: always last for those sorts.
        make_book("C", title="Gamma", authors=["Mo"], date_added="2024-02-01", runtime_length_min=60),
    ])
    db.execute("UPDATE library_books SET last_downloaded = '2026-01-01' "
               "WHERE book_id = (SELECT id FROM books WHERE audible_id = 'C')")
    return db


@pytest.mark.parametrize("sort,order,want", [
    (None, None, "BAC"),  # title, case-insensitive
    ("title", "desc", "CAB"),
    ("author", None, "BCA"),  # Amy, Mo, Zed
    ("added", None, "ACB"),  # newest first
    ("added", "asc", "BCA"),
    ("released", None, "BAC"),  # newest first, unknown last
    ("released", "asc", "ABC"),  # unknown still last
    ("length", None, "BAC"),  # longest first
    ("series", None, "BAC"),  # book 2 before book 10, no series last
    ("rating", None, "BAC"),  # unrated last
    ("downloaded", None, "CBA"),  # never downloaded last, then by title
])
def test_sort(sorted_db, sort, order, want, library_svc):
    got = "".join(b["audible_id"] for b in library_svc.list_books(sort=sort, order=order))
    assert got == want


@pytest.mark.parametrize("sort,order", [("b.id;DROP TABLE books", None), ("title", "sideways")])
def test_sort_rejects_unknown(sorted_db, sort, order, library_svc):
    with pytest.raises(library.InvalidSort):
        library_svc.list_books(sort=sort, order=order)


def test_search_matches_word_prefixes_and_tolerates_punctuation(db, library_svc):
    add_account(db)
    import_books(db, 1, [
        make_book("A", title="Atomic Habits", authors=["James Clear"]),
        make_book("B", title="Deep Work", authors=["Cal Newport"]),
    ])
    assert [b["audible_id"] for b in library_svc.list_books(search="atom")] == ["A"]
    assert [b["audible_id"] for b in library_svc.list_books(search="newport")] == ["B"]
    assert [b["audible_id"] for b in library_svc.list_books(search='"deep" (work')] == ["B"]
    assert library_svc.list_books(search="?!") == []


def test_get_and_update_book(db, library_svc):
    add_account(db)
    import_books(db, 1, [make_book("A", title="T", authors=["Au"], narrators=["Na"],
                                             series=[{"asin": "S", "title": "Saga", "sequence": "3"}])])
    book_id = db.scalar("SELECT id FROM books WHERE audible_id = 'A'")
    library_svc.update_book(book_id, tags="fav", is_finished=True, user_rating=4)
    book = library_svc.get_book(book_id)
    assert book["authors"] == ["Au"] and book["narrators"] == ["Na"]
    assert book["series"] == [{"name": "Saga", "index": "3"}]
    assert (book["tags"], book["is_finished"], book["user_rating"]) == ("fav", True, 4)
    assert library_svc.get_book(999) is None


def test_audio_files_on_disk_finds_files_in_book_folders(tmp_path):
    for rel in ["Loose Book.mp3", "P R - The Name of the Wind/The Name of the Wind.m4b",
                "P R - The Name of the Wind/The Name of the Wind.cue", ".incomplete/dl-1.out.m4b"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
    assert library.audio_files_on_disk(str(tmp_path)) == {"Loose Book": "mp3", "The Name of the Wind": "m4b"}


def test_rescan_marks_found_books_downloaded(db, config, library_svc, tmp_path):
    add_account(db)
    import_books(db, 1, [make_book("A", title="Found: Book"), make_book("B", title="Missing")])
    (tmp_path / "Someone - Found_ Book").mkdir()
    (tmp_path / "Someone - Found_ Book" / "Found_ Book.m4b").write_bytes(b"")
    config.output_dir = str(tmp_path)
    assert library_svc.rescan() == 1
    status = {r["audible_id"]: (r["liberation_status"], r["last_format"]) for r in db.query(
        "SELECT b.audible_id, lb.liberation_status, lb.last_format FROM books b "
        "JOIN library_books lb ON lb.book_id = b.id")}
    assert status == {"A": ("liberated", "m4b"), "B": ("not_liberated", None)}


def test_has_pdf_comes_from_the_sync_and_survives_a_scan_without_it(db, library_svc):
    add_account(db)
    import_books(db, 1, [make_book("A", has_pdf=True), make_book("B", has_pdf=False), make_book("C")])
    flags = {b["audible_id"]: b["has_pdf"] for b in library_svc.list_books()}
    assert flags == {"A": True, "B": False, "C": None}  # C: never synced with the flag
    import_books(db, 1, [make_book("A"), make_book("B"), make_book("C")])  # a scan without the flag
    assert {b["audible_id"]: b["has_pdf"] for b in library_svc.list_books()} == flags
    assert library_svc.get_book(db.scalar("SELECT id FROM books WHERE audible_id = 'A'"))["has_pdf"] is True
