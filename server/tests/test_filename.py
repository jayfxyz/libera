import os

from app.config import NamingPreset
from app.jobs.filename import FilenameData, book_directory, book_file_name, pad_series_index
from app.naming import MAX_NAME_BYTES, sanitize_filename

WIND = FilenameData(title="The Name of the Wind", author="Patrick Rothfuss", series_name="Kingkiller Chronicle",
                    series_index="1", year="2007", asin="B002UZMLXM")
STANDALONE = FilenameData(title="Piranesi", author="Susanna Clarke", year="2020", asin="B08FYH2QK2")


def test_each_preset():
    expected = {
        NamingPreset.TITLE: "/a/The Name of the Wind [B002UZMLXM]",
        NamingPreset.AUTHOR_FOLDER: "/a/Patrick Rothfuss/The Name of the Wind [B002UZMLXM]",
        NamingPreset.AUTHOR_FOLDER_YEAR: "/a/Patrick Rothfuss/2007 - The Name of the Wind [B002UZMLXM]",
        NamingPreset.AUTHOR_SERIES: "/a/Patrick Rothfuss/Kingkiller Chronicle/01 - The Name of the Wind [B002UZMLXM]",
        NamingPreset.AUTHOR_SERIES_YEAR: "/a/Patrick Rothfuss/Kingkiller Chronicle/01 - 2007 - The Name of the Wind [B002UZMLXM]",
    }
    assert {preset: book_directory("/a", preset, WIND) for preset in NamingPreset} == expected


def test_no_series_goes_in_author_folder():
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES, STANDALONE) == "/a/Susanna Clarke/Piranesi [B08FYH2QK2]"
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES_YEAR, STANDALONE) == "/a/Susanna Clarke/2020 - Piranesi [B08FYH2QK2]"


def test_missing_parts_leave_no_dangling_separator():
    no_year = FilenameData(title="Book", author="Jane", series_name="Saga", series_index="2", asin="B1")
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES_YEAR, no_year) == "/a/Jane/Saga/02 - Book [B1]"
    assert book_directory("/a", NamingPreset.AUTHOR_FOLDER_YEAR, no_year) == "/a/Jane/Book [B1]"
    no_index = FilenameData(title="Book", author="Jane", series_name="Saga", asin="B1")
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES, no_index) == "/a/Jane/Saga/Book [B1]"
    no_author = FilenameData(title="Book", asin="B1")
    assert book_directory("/a", NamingPreset.TITLE, no_author) == "/a/Book [B1]"
    assert book_directory("/a", NamingPreset.AUTHOR_FOLDER, no_author) == "/a/Book [B1]"


def test_file_is_named_after_the_title_and_asin():
    assert book_file_name(WIND) == "The Name of the Wind [B002UZMLXM]"


def test_books_with_the_same_title_get_different_names():
    other = FilenameData(title=WIND.title, author=WIND.author, asin="B000000001")
    for preset in NamingPreset:
        assert book_directory("/a", preset, WIND) != book_directory("/a", preset, other)
    assert book_file_name(WIND) != book_file_name(other)


def test_a_long_title_is_cut_before_the_asin():
    data = FilenameData(title="x" * 300, author="Jane", asin="B002UZMLXM")
    name = book_file_name(data)
    folder = os.path.basename(book_directory("/a", NamingPreset.TITLE, data))
    assert name.endswith(" [B002UZMLXM]") and folder.endswith(" [B002UZMLXM]")
    assert len(name.encode()) <= MAX_NAME_BYTES and len(folder.encode()) <= MAX_NAME_BYTES


def test_a_book_without_an_asin_has_no_suffix():
    assert book_file_name(FilenameData(title="Book")) == "Book"
    assert book_directory("/a", NamingPreset.AUTHOR_FOLDER, FilenameData(title="Book", author="Jane")) == "/a/Jane/Book"


def test_metadata_cannot_nest_folders():
    data = FilenameData(title="AC/DC: A Story", author="A/B", asin="B1")
    assert book_directory("/a", NamingPreset.AUTHOR_FOLDER, data) == "/a/A_B/AC_DC - A Story [B1]"


def test_sanitize_filename():
    assert sanitize_filename("Dune: Part One") == "Dune - Part One"
    assert sanitize_filename('H<G> "x"?') == "H_G_ _x__"
    assert sanitize_filename("..") == "audiobook"  # never the parent folder
    assert sanitize_filename(".hidden") == "hidden"
    assert sanitize_filename("Smith Jr.  ") == "Smith Jr"  # Windows and SMB reject trailing dots and spaces
    long = sanitize_filename("é" * 300)  # 2 bytes each
    assert len(long.encode()) <= 200 and long == "é" * 100


def test_series_index_is_padded_so_books_sort_in_order():
    assert [pad_series_index(i) for i in ("1", "10", "2.5", "100", "0.5", "", "Book 1", "1a")] == [
        "01", "10", "02.5", "100", "00.5", "", "Book 1", "1a"]
