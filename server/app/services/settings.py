"""User settings: environment defaults overlaid by values saved in the database."""

from __future__ import annotations

from typing import Any

from ..config import FORMATS, MAX_DOWNLOAD_WORKERS, Config
from ..db import Database
from ..repositories import books as books_repo
from ..repositories import settings as repo

LAYOUT_DIALOG_SEEN = "layout_dialog_seen"  # saved once the "Library structure matters" dialog was answered


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
            self._skip_layout_dialog_without_downloads(s)

    def _skip_layout_dialog_without_downloads(self, s) -> None:
        """The dialog is for people upgrading with books on disk. A new install already gets the recommended layout."""
        if repo.get(s, LAYOUT_DIALOG_SEEN) is None and not books_repo.has_downloaded_books(s):
            repo.set(s, LAYOUT_DIALOG_SEEN, "true")

    def current(self) -> dict[str, Any]:
        c = self._config
        with self._db.session() as s:
            layout_dialog_pending = repo.get(s, LAYOUT_DIALOG_SEEN) != "true"
        return {
            "output_dir": c.output_dir,
            "download_workers": c.download_workers,
            "default_format": c.default_format,
            "naming": c.naming.value,
            "layout_dialog_pending": layout_dialog_pending,
        }

    def update(self, changes: dict[str, Any]) -> None:
        """Save and apply changed settings (None values are ignored)."""
        changes = {k: v for k, v in changes.items() if v is not None}
        if "default_format" in changes and changes["default_format"] not in FORMATS:
            raise InvalidSetting("default_format must be 'm4b' or 'mp3'")
        if "download_workers" in changes and not 1 <= changes["download_workers"] <= MAX_DOWNLOAD_WORKERS:
            raise InvalidSetting(f"download_workers must be between 1 and {MAX_DOWNLOAD_WORKERS}")
        layout_dialog_seen = changes.pop("layout_dialog_seen", None)
        with self._db.session() as s:
            for key, value in changes.items():
                repo.set(s, key, str(value))
            if layout_dialog_seen is not None:
                repo.set(s, LAYOUT_DIALOG_SEEN, "true" if layout_dialog_seen else "false")
        for key, value in changes.items():
            self._config.apply(key, str(value))
