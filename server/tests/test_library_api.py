import csv
import io

from tests.conftest import add_account, make_book
from app import library


def seed(db):
    add_account(db)
    library.import_library(db, 1, [make_book("EX01", title="One", authors=["A"]), make_book("EX02", title="Two")])


def test_list_and_sort(client, db):
    seed(db)
    assert [b["audible_id"] for b in client.get("/api/library").json()] == ["EX01", "EX02"]
    assert [b["audible_id"] for b in client.get("/api/library?sort=title&order=desc").json()] == ["EX02", "EX01"]
    assert client.get("/api/library?sort=nope").status_code == 400
    book = client.get("/api/library").json()[0]
    assert set(book) == {"id", "audible_id", "title", "cover_url", "liberation_status", "is_finished",
                         "is_deleted", "is_hidden", "tags", "account_id", "authors", "narrators", "genres",
                         "last_format", "length_minutes", "date_added"}
    assert (book["authors"], book["is_hidden"]) == (["A"], False)
    assert book["is_finished"] is False


def test_detail_update_and_404(client, db):
    seed(db)
    book_id = client.get("/api/library").json()[0]["id"]
    assert client.patch(f"/api/library/{book_id}", json={"is_finished": True}).status_code == 204
    detail = client.get(f"/api/library/{book_id}").json()
    assert detail["is_finished"] is True and detail["authors"] == ["A"]
    assert client.get("/api/library/999").status_code == 404


def test_export_json(client, db):
    seed(db)
    resp = client.get("/api/library/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert [r["audible_id"] for r in resp.json()] == ["EX01", "EX02"]


def test_export_csv(client, db):
    seed(db)
    resp = client.get("/api/library/export?format=csv")
    assert resp.headers["content-type"].startswith("text/csv")
    records = list(csv.reader(io.StringIO(resp.text)))
    assert records[0] == library.EXPORT_FIELDS
    assert len(records) == 3
    assert records[1][:3] == ["EX01", "One", "A"]
    assert records[1][10] == "false"  # is_finished


def test_export_rejects_unknown_format(client):
    assert client.get("/api/library/export?format=xml").status_code == 400


def test_rescan_endpoint(client, db, config, tmp_path):
    seed(db)
    import os
    os.makedirs(config.output_dir)
    open(os.path.join(config.output_dir, "One.m4b"), "wb").close()
    assert client.post("/api/library/rescan").json() == {"matched": 1}
