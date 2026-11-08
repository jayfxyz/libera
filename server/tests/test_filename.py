from app.jobs.filename import FilenameData, book_directory, render_filename


def test_default_template():
    assert render_filename("{title}", FilenameData(title="The Great Gatsby", authors="F. Scott")) == "The Great Gatsby"


def test_all_tags():
    data = FilenameData(title="Dune", authors="Frank Herbert", narrators="Scott Brick", series_name="Dune Chronicles",
                        series_index="1", year="1965", language="english", duration_h="21")
    got = render_filename("{author} - {series} {series_index} - {title} ({year}) [{narrator}]", data)
    assert got == "Frank Herbert - Dune Chronicles 1 - Dune (1965) [Scott Brick]"


def test_missing_tag_drops_its_separator():
    assert render_filename("{title} - {series}", FilenameData(title="Book")) == "Book"
    assert render_filename("{author} - {title}", FilenameData(title="Book")) == "Book"


def test_unsafe_characters_replaced():
    got = render_filename("{title}", FilenameData(title="H/G: A <Tale>"))
    assert not set("/<>:") & set(got)


def test_empty_template_falls_back_to_title():
    assert render_filename("", FilenameData(title="Fallback")) == "Fallback"


def test_book_directory():
    data = FilenameData(title="The Name of the Wind", authors="Patrick Rothfuss")
    assert book_directory("/audiobooks", "{author} - {title}", data) == "/audiobooks/Patrick Rothfuss - The Name of the Wind"
    assert book_directory("/audiobooks", "", data) == "/audiobooks"
    assert book_directory("/audiobooks", "  ", data) == "/audiobooks"
    # Missing author: no dangling separator; "/" in metadata can't nest folders.
    assert book_directory("/audiobooks", "{author} - {title}", FilenameData(title="AC/DC: A Story")) == "/audiobooks/AC_DC_ A Story"
