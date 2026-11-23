"""Application configuration: environment defaults, overlaid by settings saved in the DB."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import StrEnum

FORMATS = ("m4b", "mp3")
MAX_DOWNLOAD_WORKERS = 5  # more mostly gets Audible to throttle the account

# Settings the user can change from the UI; persisted in the `settings` table.
EDITABLE_KEYS = ("download_workers", "default_format", "naming")


class NamingPreset(StrEnum):
    """Where a book's files go inside the output folder. The audio file is always named after the title.
    The nested layouts are the ones Audiobookshelf reads authors, series and order from."""

    AUTHOR_TITLE = "author_title"  # Author - Title/
    AUTHOR_FOLDER = "author_folder"  # Author/Title/
    AUTHOR_FOLDER_YEAR = "author_folder_year"  # Author/2007 - Title/
    AUTHOR_SERIES = "author_series"  # Author/Series/1 - Title/
    AUTHOR_SERIES_YEAR = "author_series_year"  # Author/Series/1 - 2007 - Title/


@dataclass
class Config:
    database_path: str = "./data/db/libera.db"
    accounts_dir: str = "./data/accounts"
    frontend_dir: str = ""  # built Vue app; empty = don't serve it
    app_url: str = "http://localhost:8080"
    output_dir: str = "./data/audiobooks"
    download_workers: int = 3
    default_format: str = "m4b"
    naming: NamingPreset = NamingPreset.AUTHOR_TITLE

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        c = cls()
        c.database_path = env.get("DATABASE_PATH", c.database_path)
        c.accounts_dir = env.get("ACCOUNTS_DIR", c.accounts_dir)
        c.frontend_dir = env.get("FRONTEND_DIR", c.frontend_dir)
        c.app_url = env.get("APP_URL", c.app_url)
        c.output_dir = env.get("OUTPUT_DIR", c.output_dir)  # set by the container's mount, not the UI
        for key in EDITABLE_KEYS:
            if key.upper() in env:
                c.apply(key, env[key.upper()])
        return c

    def apply(self, key: str, value: str) -> None:
        """Set one editable setting from its stored string form; invalid values are ignored."""
        if key == "download_workers":
            try:
                n = int(value)
            except ValueError:
                return
            if 1 <= n <= MAX_DOWNLOAD_WORKERS:
                self.download_workers = n
        elif key == "default_format":
            if value in FORMATS:
                self.default_format = value
        elif key == "naming":
            if value in NamingPreset:
                self.naming = NamingPreset(value)

    def apply_overrides(self, overrides: dict[str, str]) -> None:
        for key in EDITABLE_KEYS:
            if key in overrides:
                self.apply(key, overrides[key])

    def snapshot(self) -> "Config":
        """A copy for a job to use, so later setting changes don't affect it."""
        return replace(self)
