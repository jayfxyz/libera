import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def site(tmp_path, config, db):
    (tmp_path / "dist" / "assets").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text("<!doctype html><div id=app></div>")
    (tmp_path / "dist" / "assets" / "index-AbC123.js").write_text("console.log('x');" * 200)
    config.frontend_dir = str(tmp_path / "dist")
    with TestClient(create_app(config, db)) as c:
        yield c


def test_index_is_revalidated(site):
    r = site.get("/")
    assert r.status_code == 200 and "id=app" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_immutable_and_compressed(site):
    r = site.get("/assets/index-AbC123.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["content-encoding"] == "gzip"


def test_old_path_links_open_the_app(site):
    r = site.get("/settings")
    assert r.status_code == 200 and "id=app" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_api_and_missing_files_still_404(site):
    assert site.get("/api/nope").status_code == 404
    assert site.get("/assets/missing-123.js").status_code == 404
    assert site.get("/favicon.ico").status_code == 404


def test_api_routes_win_over_static_files(site):
    assert site.get("/api/settings").json()["default_format"] == "m4b"
    assert site.get("/health").text == "ok"
