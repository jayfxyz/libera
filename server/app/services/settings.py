"""User settings: environment defaults overlaid by values saved in the database."""

from __future__ import annotations

from typing import Any

from ..config import FORMATS, Config
from ..db import Database
from ..repositories import settings as repo


class InvalidSetting(ValueError):
    pass


def load_saved(db: Database, config: Config) -> None:
    """Apply saved settings over the environment defaults (at startup)."""
    with db.session() as s:
        config.apply_overrides(repo.all(s))


def current(config: Config) -> dict[str, Any]:
    return {
        "app_url": config.app_url,
        "output_dir": config.output_dir,
        "download_workers": config.download_workers,
        "default_format": config.default_format,
        "filename_template": config.filename_template,
        "folder_template": config.folder_template,
    }


def update(db: Database, config: Config, changes: dict[str, Any]) -> None:
    """Save and apply changed settings (None values are ignored)."""
    changes = {k: v for k, v in changes.items() if v is not None}
    if "default_format" in changes and changes["default_format"] not in FORMATS:
        raise InvalidSetting("default_format must be 'm4b' or 'mp3'")
    with db.session() as s:
        for key, value in changes.items():
            repo.set(s, key, str(value))
    for key, value in changes.items():
        config.apply(key, str(value))
