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


def test_a_book_in_two_accounts_is_one_row_unless_filtering_by_account(db, library_svc):
    add_account(db, 1)
    add_account(db, 2, audible_account_id="amzn1.account.OTHER")
    import_books(db, 1, [make_book("S", title="Shared", date_added="2021-11-19"), make_book("A", title="Mine")])
    import_books(db, 2, [make_book("S", title="Shared", date_added="2021-11-27")])

    rows = library_svc.list_books()
    assert sorted((b["audible_id"], b["account_ids"]) for b in rows) == [("A", [1]), ("S", [1, 2])]
    shared = next(b for b in rows if b["audible_id"] == "S")
    assert shared == library_svc.book_summary(shared["id"])  # the same entry book.updated events describe
    assert [b["audible_id"] for b in library_svc.list_books(search="shared")] == ["S"]

    assert [(b["audible_id"], b["account_id"]) for b in library_svc.list_books(account_id=2)] == [("S", 2)]
    assert sorted(b["audible_id"] for b in library_svc.list_books(account_id=1)) == ["A", "S"]


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
    import_books(db, 1, [make_book("A", title="Found: Book"), make_book("B", title="Missing"),
                         make_book("C", title="Nested: Book")])
    (tmp_path / "Someone - Found_ Book").mkdir()
    (tmp_path / "Someone - Found_ Book" / "Found_ Book.m4b").write_bytes(b"")  # named before ":" became " -"
    (tmp_path / "Someone" / "Nested - Book").mkdir(parents=True)
    (tmp_path / "Someone" / "Nested - Book" / "Nested - Book.mp3").write_bytes(b"")
    config.output_dir = str(tmp_path)
    assert library_svc.rescan() == 2
    status = {r["audible_id"]: (r["liberation_status"], r["last_format"]) for r in db.query(
        "SELECT b.audible_id, lb.liberation_status, lb.last_format FROM books b "
        "JOIN library_books lb ON lb.book_id = b.id")}
    assert status == {"A": ("liberated", "m4b"), "B": ("not_liberated", None), "C": ("liberated", "mp3")}


def test_has_pdf_comes_from_the_sync_and_survives_a_scan_without_it(db, library_svc):
    add_account(db)
    import_books(db, 1, [make_book("A", has_pdf=True), make_book("B", has_pdf=False), make_book("C")])
    flags = {b["audible_id"]: b["has_pdf"] for b in library_svc.list_books()}
    assert flags == {"A": True, "B": False, "C": None}  # C: never synced with the flag
    import_books(db, 1, [make_book("A"), make_book("B"), make_book("C")])  # a scan without the flag
    assert {b["audible_id"]: b["has_pdf"] for b in library_svc.list_books()} == flags
    assert library_svc.get_book(db.scalar("SELECT id FROM books WHERE audible_id = 'A'"))["has_pdf"] is True


def test_is_downloadable_tracked_and_updated_on_rescan(db, library_svc):
    from app.audible_api.models import AudibleBook

    locked = AudibleBook.from_audible({
        "asin": "LOCKED", "title": "Borrowed",
        "customer_rights": {"is_consumable_offline": False},
    })
    owned = AudibleBook.from_audible({
        "asin": "OWNED", "title": "Bought",
        "customer_rights": {"is_consumable_offline": True},
    })
    assert locked.is_downloadable is False and owned.is_downloadable is True

    add_account(db)
    library_svc.import_library(1, [locked, owned])
    flags = {b["audible_id"]: b["is_downloadable"] for b in library_svc.list_books()}
    assert flags == {"LOCKED": False, "OWNED": True}
    locked_id = db.scalar("SELECT id FROM books WHERE audible_id = 'LOCKED'")
    assert library_svc.get_book(locked_id)["is_downloadable"] is False

    # Re-scanning after purchasing/renewing flips it back to downloadable.
    unlocked = AudibleBook.from_audible({
        "asin": "LOCKED", "title": "Borrowed",
        "customer_rights": {"is_consumable_offline": True},
    })
    library_svc.import_library(1, [unlocked, owned])
    assert library_svc.get_book(locked_id)["is_downloadable"] is True


def test_non_downloadable_books_rejected_single_and_skipped_in_bulk(db, config, library_svc):
    from unittest.mock import MagicMock
    import pytest
    from app.events import EventBus
    from app.services.downloads import DownloadsService, InvalidOptions
    from app.services.task_queue import TaskQueueService
    from app.tasks.signals import TaskSignals

    add_account(db)
    import_books(db, 1, [make_book("OK", title="Owned"), make_book("NO", title="Locked", is_downloadable=False)])
    ok_id = db.scalar("SELECT id FROM books WHERE audible_id = 'OK'")
    no_id = db.scalar("SELECT id FROM books WHERE audible_id = 'NO'")

    downloads = DownloadsService(db, config, TaskQueueService(db, TaskSignals()), EventBus(), MagicMock(), library_svc)
    with pytest.raises(InvalidOptions, match="not downloadable"):
        downloads.enqueue(no_id)

    queued = downloads.enqueue_many([no_id, ok_id])
    assert [q["book_id"] for q in queued] == [ok_id]


def test_multi_account_prefers_downloadable_copy(db, config, library_svc):
    from unittest.mock import MagicMock
    import pytest
    from app.events import EventBus
    from app.services.downloads import DownloadsService, InvalidOptions
    from app.services.task_queue import TaskQueueService
    from app.tasks.signals import TaskSignals

    add_account(db, 1, "acct-locked")
    add_account(db, 2, "acct-owned")
    import_books(db, 1, [make_book("SHARED", title="Shared Book", is_downloadable=False)])
    import_books(db, 2, [make_book("SHARED", title="Shared Book", is_downloadable=True)])

    book_id = db.scalar("SELECT id FROM books WHERE audible_id = 'SHARED'")
    # Combined view and detail prefer the downloadable account (account 2).
    combined = library_svc.list_books()[0]
    assert combined["is_downloadable"] is True and combined["account_id"] == 2
    assert library_svc.get_book(book_id)["is_downloadable"] is True
    # Filtering to account 1 still shows its locked state.
    assert library_svc.list_books(account_id=1)[0]["is_downloadable"] is False

    downloads = DownloadsService(db, config, TaskQueueService(db, TaskSignals()), EventBus(), MagicMock(), library_svc)
    assert library_svc.book_meta(book_id)["account_id"] == 2
    assert downloads.enqueue(book_id) is not None
    with pytest.raises(InvalidOptions, match="not downloadable"):
        downloads.enqueue(book_id, account_id=1)
