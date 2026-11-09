from app.config import DEFAULT_FOLDER_TEMPLATE, Config
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
    assert get_setting(db, "output_dir") is None
    set_setting(db, "output_dir", "/audiobooks")
    assert get_setting(db, "output_dir") == "/audiobooks"
    set_setting(db, "output_dir", "/new/path")
    assert get_setting(db, "output_dir") == "/new/path"


def test_settings_load_all(db):
    for k, v in {"output_dir": "/a", "default_format": "mp3", "download_workers": "5"}.items():
        set_setting(db, k, v)
    assert all_settings(db) == {"output_dir": "/a", "default_format": "mp3", "download_workers": "5"}


def test_config_from_env_and_overrides():
    c = Config.from_env({"OUTPUT_DIR": "/audiobooks", "DOWNLOAD_WORKERS": "2", "DEFAULT_FORMAT": "flac"})
    assert c.output_dir == "/audiobooks"
    assert c.download_workers == 2
    assert c.default_format == "m4b"  # invalid value ignored
    assert c.folder_template == DEFAULT_FOLDER_TEMPLATE

    c.apply_overrides({"default_format": "mp3", "download_workers": "0", "folder_template": ""})
    assert c.default_format == "mp3"
    assert c.download_workers == 2  # must be positive
    assert c.folder_template == ""  # empty is valid: no per-book folder


def test_settings_api(client, db):
    got = client.get("/api/settings").json()
    assert got["default_format"] == "m4b"
    assert got["folder_template"] == DEFAULT_FOLDER_TEMPLATE

    # The UI sends the whole object back, including read-only app_url.
    resp = client.patch("/api/settings", json={**got, "default_format": "mp3", "folder_template": "{title}"})
    assert resp.status_code == 204
    assert get_setting(db, "default_format") == "mp3"
    assert get_setting(db, "app_url") is None

    got = client.get("/api/settings").json()
    assert got["default_format"] == "mp3"
    assert got["folder_template"] == "{title}"


def test_settings_api_rejects_bad_format(client):
    assert client.patch("/api/settings", json={"default_format": "wav"}).status_code == 400


def test_saved_settings_apply_at_startup(config, db):
    from fastapi.testclient import TestClient
    from app.main import create_app

    set_setting(db, "filename_template", "{author} - {title}")
    with TestClient(create_app(config, db)) as c:
        assert c.get("/api/settings").json()["filename_template"] == "{author} - {title}"


def test_health(client):
    assert client.get("/health").text == "ok"


def test_iso_utc():
    from app.db import iso_utc
    assert iso_utc("2026-11-08 23:00:51") == "2026-11-08T23:00:51Z"
    assert iso_utc("2021-12-27T21:39:12.000Z") == "2021-12-27T21:39:12.000Z"
    assert iso_utc(None) is None
