from app.config import NamingPreset
from app.jobs.filename import FilenameData, book_directory, book_file_name
from app.services.library import sanitize_filename

WIND = FilenameData(title="The Name of the Wind", author="Patrick Rothfuss", series_name="Kingkiller Chronicle",
                    series_index="1", year="2007")
STANDALONE = FilenameData(title="Piranesi", author="Susanna Clarke", year="2020")


def test_each_preset():
    expected = {
        NamingPreset.AUTHOR_TITLE: "/a/Patrick Rothfuss - The Name of the Wind",
        NamingPreset.AUTHOR_FOLDER: "/a/Patrick Rothfuss/The Name of the Wind",
        NamingPreset.AUTHOR_FOLDER_YEAR: "/a/Patrick Rothfuss/2007 - The Name of the Wind",
        NamingPreset.AUTHOR_SERIES: "/a/Patrick Rothfuss/Kingkiller Chronicle/1 - The Name of the Wind",
        NamingPreset.AUTHOR_SERIES_YEAR: "/a/Patrick Rothfuss/Kingkiller Chronicle/1 - 2007 - The Name of the Wind",
    }
    assert {preset: book_directory("/a", preset, WIND) for preset in NamingPreset} == expected


def test_no_series_goes_in_author_title():
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES, STANDALONE) == "/a/Susanna Clarke/Piranesi"
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES_YEAR, STANDALONE) == "/a/Susanna Clarke/2020 - Piranesi"


def test_missing_parts_leave_no_dangling_separator():
    no_year = FilenameData(title="Book", author="Jane", series_name="Saga", series_index="2")
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES_YEAR, no_year) == "/a/Jane/Saga/2 - Book"
    assert book_directory("/a", NamingPreset.AUTHOR_FOLDER_YEAR, no_year) == "/a/Jane/Book"
    no_index = FilenameData(title="Book", author="Jane", series_name="Saga")
    assert book_directory("/a", NamingPreset.AUTHOR_SERIES, no_index) == "/a/Jane/Saga/Book"
    no_author = FilenameData(title="Book")
    assert book_directory("/a", NamingPreset.AUTHOR_TITLE, no_author) == "/a/Book"
    assert book_directory("/a", NamingPreset.AUTHOR_FOLDER, no_author) == "/a/Book"


def test_file_is_named_after_the_title():
    assert book_file_name(WIND) == "The Name of the Wind"


def test_metadata_cannot_nest_folders():
    data = FilenameData(title="AC/DC: A Story", author="A/B")
    assert book_directory("/a", NamingPreset.AUTHOR_FOLDER, data) == "/a/A_B/AC_DC - A Story"


def test_sanitize_filename():
    assert sanitize_filename("Dune: Part One") == "Dune - Part One"
    assert sanitize_filename('H<G> "x"?') == "H_G_ _x__"
    assert sanitize_filename("..") == "audiobook"  # never the parent folder
    assert sanitize_filename(".hidden") == "hidden"
    assert sanitize_filename("Smith Jr.  ") == "Smith Jr"  # Windows and SMB reject trailing dots and spaces
    long = sanitize_filename("é" * 300)  # 2 bytes each
    assert len(long.encode()) <= 200 and long == "é" * 100
