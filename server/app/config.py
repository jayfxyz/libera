"""Application configuration: environment defaults, overlaid by settings saved in the DB."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

DEFAULT_FOLDER_TEMPLATE = "{author} - {title}"  # "Patrick Rothfuss - The Name of the Wind"
FORMATS = ("m4b", "mp3")

# Settings the user can change from the UI; persisted in the `settings` table.
EDITABLE_KEYS = ("output_dir", "download_workers", "default_format", "filename_template", "folder_template")


@dataclass
class Config:
    database_path: str = "./data/db/libation.db"
    accounts_dir: str = "./data/accounts"
    frontend_dir: str = ""  # built Vue app; empty = don't serve it
    app_url: str = "http://localhost:8080"
    output_dir: str = "./data/audiobooks"
    download_workers: int = 3
    default_format: str = "m4b"
    filename_template: str = "{title}"
    folder_template: str = DEFAULT_FOLDER_TEMPLATE

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        c = cls()
        c.database_path = env.get("DATABASE_PATH", c.database_path)
        c.accounts_dir = env.get("ACCOUNTS_DIR", c.accounts_dir)
        c.frontend_dir = env.get("FRONTEND_DIR", c.frontend_dir)
        c.app_url = env.get("APP_URL", c.app_url)
        for key in EDITABLE_KEYS:
            if key.upper() in env:
                c.apply(key, env[key.upper()])
        return c

    def apply(self, key: str, value: str) -> None:
        """Set one editable setting from its stored string form; invalid values are ignored."""
        if key == "output_dir":
            self.output_dir = value
        elif key == "download_workers":
            try:
                n = int(value)
            except ValueError:
                return
            if n > 0:
                self.download_workers = n
        elif key == "default_format":
            if value in FORMATS:
                self.default_format = value
        elif key == "filename_template":
            self.filename_template = value
        elif key == "folder_template":
            self.folder_template = value

    def apply_overrides(self, overrides: dict[str, str]) -> None:
        for key in EDITABLE_KEYS:
            if key in overrides:
                self.apply(key, overrides[key])

    def snapshot(self) -> "Config":
        """A copy for a job to use, so later setting changes don't affect it."""
        return replace(self)
