"""Which database objects Alembic's autogenerate compares."""


def include_object(obj, name, type_, reflected, compare_to):
    """Leave the full-text index (books_fts and SQLite's books_fts_* shadow tables)
    out of autogenerate: it isn't modelled, so it would otherwise be "dropped"."""
    return not (type_ == "table" and name and name.startswith("books_fts"))
