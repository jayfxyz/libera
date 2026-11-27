"""The companion PDF on its own: POST /api/library/{id}/pdf."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.audible_api.content import ContentError
from app.main import create_app
from app.repositories import downloads as downloads_repo
from tests.conftest import add_account, make_book, import_books

PDF = b"%PDF-1.4 test"


class PdfAudible:
    def __init__(self):
        self.pdf, self.error = PDF, ""

    async def get_pdf(self, account_id, asin):
        if self.error:
            raise ContentError(self.error)
        return self.pdf

    async def get_download_info(self, account_id, asin):
        raise AssertionError("saving a PDF must not request a license")


@pytest.fixture
def audible():
    return PdfAudible()


@pytest.fixture
def api(config, db, audible, pipeline):
    with TestClient(create_app(config, db, audible=audible, pipeline=pipeline)) as c:
        yield c


@pytest.fixture
def book_id(db):
    add_account(db)
    import_books(db, 1, [make_book("B1", title="The Book", authors=["Jane Author"])])
    return db.scalar("SELECT id FROM books")


def test_saves_the_pdf_where_a_download_would_go(api, db, config, book_id):
    resp = api.post(f"/api/library/{book_id}/pdf")
    path = os.path.join(config.output_dir, "Jane Author", "The Book [B1]", "The Book [B1].pdf")
    assert (resp.status_code, resp.json()) == (200, {"file_path": path})
    with open(path, "rb") as f:
        assert f.read() == PDF
    assert db.scalar("SELECT COUNT(*) FROM downloads") == db.scalar("SELECT COUNT(*) FROM tasks") == 0  # not a download


def test_saves_the_pdf_next_to_the_audiobook(api, db, tmp_path, book_id, library_svc):
    library_svc.mark_downloaded(book_id, "m4b", str(tmp_path / "elsewhere" / "Old Name.m4b"))
    resp = api.post(f"/api/library/{book_id}/pdf")
    assert resp.json() == {"file_path": str(tmp_path / "elsewhere" / "Old Name.pdf")}
    assert (tmp_path / "elsewhere" / "Old Name.pdf").read_bytes() == PDF


def test_a_title_without_a_pdf_is_a_404(api, audible, book_id):
    audible.pdf = None
    resp = api.post(f"/api/library/{book_id}/pdf")
    assert resp.status_code == 404 and "no companion PDF" in resp.json()["detail"]


def test_an_audible_failure_is_a_502(api, audible, book_id):
    audible.error = "Audible couldn't look up this book: 404"
    resp = api.post(f"/api/library/{book_id}/pdf")
    assert (resp.status_code, resp.json()["detail"]) == (502, "Audible couldn't look up this book: 404")


def test_an_unknown_book_is_a_404(api):
    assert api.post("/api/library/999/pdf").status_code == 404


def test_updates_the_manifest_of_a_finished_download(api, db, config, book_id, library_svc):
    folder = os.path.join(config.output_dir, "Jane Author", "The Book")
    audio = {"role": "audio", "name": "The Book.m4b", "size_bytes": 10}
    with db.session() as s:
        downloads_repo.add(s, id="d1", library_book_id=db.scalar("SELECT id FROM library_books"), format="m4b",
                           split_chapters=False, path=folder, base_name="The Book", task_id=None)
        downloads_repo.finish(s, "d1", json.dumps([audio]))
    library_svc.mark_downloaded(book_id, "m4b", os.path.join(folder, "The Book.m4b"))

    for _ in range(2):  # saving again replaces the entry
        assert api.post(f"/api/library/{book_id}/pdf").status_code == 200
    assert json.loads(db.scalar("SELECT files FROM downloads WHERE id = 'd1'")) == [
        audio, {"role": "pdf", "name": "The Book.pdf", "size_bytes": len(PDF)}]
