from tests.conftest import add_account, import_books, make_book
from app.config import Config, NamingPreset
from app.repositories import settings as settings_repo


def get_setting(db, key):
    with db.session() as s:
        return settings_repo.get(s, key)


def set_setting(db, key, value):
    with db.session() as s:
        settings_repo.set(s, key, value)


def all_settings(db):
    with db.session() as s:
        return settings_repo.all(s)


def test_settings_roundtrip(db):
    assert get_setting(db, "naming") is None
    set_setting(db, "naming", "author_folder")
    assert get_setting(db, "naming") == "author_folder"
    set_setting(db, "naming", "author_series")
    assert get_setting(db, "naming") == "author_series"


def test_settings_load_all(db):
    for k, v in {"naming": "author_folder", "default_format": "mp3", "download_workers": "5"}.items():
        set_setting(db, k, v)
    assert all_settings(db) == {"naming": "author_folder", "default_format": "mp3", "download_workers": "5"}


def test_config_from_env_and_overrides():
    c = Config.from_env({"OUTPUT_DIR": "/audiobooks", "DOWNLOAD_WORKERS": "2", "DEFAULT_FORMAT": "flac"})
    assert c.output_dir == "/audiobooks"
    assert c.download_workers == 2
    assert c.default_format == "m4b"  # invalid value ignored
    assert c.naming == NamingPreset.AUTHOR_FOLDER

    c.apply_overrides({"default_format": "mp3", "download_workers": "0", "naming": "author_series"})
    assert c.default_format == "mp3"
    assert c.download_workers == 2  # must be positive
    c.apply_overrides({"download_workers": "20"})
    assert c.download_workers == 2  # at most MAX_DOWNLOAD_WORKERS
    assert c.naming == NamingPreset.AUTHOR_SERIES
    c.apply_overrides({"naming": "{author}/{title}"})
    assert c.naming == NamingPreset.AUTHOR_SERIES  # only presets

    c.apply_overrides({"output_dir": "/elsewhere"})
    assert c.output_dir == "/audiobooks"  # only the environment sets the output folder


def test_settings_api(client, db):
    got = client.get("/api/settings").json()
    assert got["default_format"] == "m4b"
    assert got["naming"] == "author_folder"

    # The UI sends the whole object back, including read-only output_dir.
    resp = client.patch("/api/settings", json={**got, "default_format": "mp3", "naming": "author_series",
                                               "output_dir": "/elsewhere"})
    assert resp.status_code == 204
    assert get_setting(db, "default_format") == "mp3"
    assert get_setting(db, "output_dir") is None

    got = client.get("/api/settings").json()
    assert got["default_format"] == "mp3"
    assert got["naming"] == "author_series"


def test_settings_api_rejects_bad_format(client):
    assert client.patch("/api/settings", json={"default_format": "wav"}).status_code == 400


def test_settings_api_rejects_unknown_naming(client):
    assert client.patch("/api/settings", json={"naming": "{author}/{title}"}).status_code == 422


def test_settings_api_rejects_too_many_workers(client):
    assert client.patch("/api/settings", json={"download_workers": 6}).status_code == 400
    assert client.patch("/api/settings", json={"download_workers": 0}).status_code == 400
    assert client.patch("/api/settings", json={"download_workers": 5}).status_code == 204


def test_saved_settings_apply_at_startup(config, db):
    from fastapi.testclient import TestClient
    from app.main import create_app

    set_setting(db, "naming", "author_folder_year")
    with TestClient(create_app(config, db)) as c:
        assert c.get("/api/settings").json()["naming"] == "author_folder_year"


def test_health(client):
    assert client.get("/health").text == "ok"


def test_iso_utc():
    from app.db import iso_utc
    assert iso_utc("2026-11-08 23:00:51") == "2026-11-08T23:00:51Z"
    assert iso_utc("2021-12-27T21:39:12.000Z") == "2021-12-27T21:39:12.000Z"
    assert iso_utc(None) is None


def test_the_old_flat_layout_name_still_loads():
    c = Config()
    c.apply("naming", "author_title")
    assert c.naming == NamingPreset.TITLE


def test_layout_dialog_is_skipped_on_a_fresh_install(client):
    assert client.get("/api/settings").json()["layout_dialog_pending"] is False


def test_layout_dialog_waits_for_people_upgrading_with_downloads(config, db):
    from fastapi.testclient import TestClient
    from app.main import create_app

    add_account(db)
    import_books(db, 1, [make_book("A1")])
    db.execute("UPDATE library_books SET download_status = 'downloaded'")
    with TestClient(create_app(config, db)) as c:
        assert c.get("/api/settings").json()["layout_dialog_pending"] is True
        assert c.patch("/api/settings", json={"layout_dialog_seen": True}).status_code == 204
        assert c.get("/api/settings").json()["layout_dialog_pending"] is False
