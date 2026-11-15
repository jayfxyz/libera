"""User settings: environment defaults overlaid by values saved in the database."""

from __future__ import annotations

from typing import Any

from ..config import FORMATS, Config
from ..db import Database
from ..repositories import settings as repo


class InvalidSetting(ValueError):
    pass


class SettingsService:
    def __init__(self, db: Database, config: Config):
        self._db = db
        self._config = config

    def load_saved(self) -> None:
        """Apply saved settings over the environment defaults (at startup)."""
        with self._db.session() as s:
            self._config.apply_overrides(repo.all(s))

    def current(self) -> dict[str, Any]:
        c = self._config
        return {
            "app_url": c.app_url,
            "output_dir": c.output_dir,
            "download_workers": c.download_workers,
            "default_format": c.default_format,
            "filename_template": c.filename_template,
            "folder_template": c.folder_template,
        }

    def update(self, changes: dict[str, Any]) -> None:
        """Save and apply changed settings (None values are ignored)."""
        changes = {k: v for k, v in changes.items() if v is not None}
        if "default_format" in changes and changes["default_format"] not in FORMATS:
            raise InvalidSetting("default_format must be 'm4b' or 'mp3'")
        with self._db.session() as s:
            for key, value in changes.items():
                repo.set(s, key, str(value))
        for key, value in changes.items():
            self._config.apply(key, str(value))
