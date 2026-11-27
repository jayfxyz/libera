"""Moving downloaded books to another folder layout.

Only whole book folders move, and only ones Libera can be sure belong to a single book: the folder and the audio
file are both named with the book's Audible ID. Anything else is left where it is and reported."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..config import Config
from ..db import Database
from ..jobs.filename import FilenameData, book_directory
from ..naming import ASIN_SUFFIX
from ..repositories import books as books_repo
from ..repositories import downloads as downloads_repo
from .library import LibraryService, naming_data

log = logging.getLogger(__name__)

EXAMPLE_COUNT = 3
SKIPPED_SHOWN = 20


class Outcome(StrEnum):
    MOVE = "move"
    IN_PLACE = "in_place"
    NO_ID_IN_NAME = "no_id_in_name"
    FILE_MISSING = "file_missing"
    NOT_IN_OWN_FOLDER = "not_in_own_folder"
    TARGET_EXISTS = "target_exists"
    DOWNLOADING = "downloading"
    FAILED = "failed"


REASONS = {
    Outcome.NO_ID_IN_NAME: "The folder or file name has no Audible ID",
    Outcome.FILE_MISSING: "The file is not on disk",
    Outcome.NOT_IN_OWN_FOLDER: "It is not in a folder of its own",
    Outcome.TARGET_EXISTS: "A folder with the new name already exists",
    Outcome.DOWNLOADING: "It is downloading now",
    Outcome.FAILED: "The folder could not be moved",
}


class MoveInProgress(RuntimeError):
    pass


@dataclass
class MovePlan:
    book_id: int
    title: str
    outcome: Outcome
    file_path: str
    old_dir: str
    new_dir: str


def inside(root: str, path: str) -> bool:
    return os.path.commonpath([root, path]) == root and path != root


def judge(book: dict[str, Any], new_dir: str, output_dir: str, downloading: bool) -> Outcome:
    """What can safely be done with one book's folder."""
    file_path = book["file_path"]
    old_dir = os.path.dirname(file_path)
    if downloading:
        return Outcome.DOWNLOADING
    if not os.path.isfile(file_path):
        return Outcome.FILE_MISSING
    if not inside(output_dir, old_dir) or os.path.islink(old_dir):
        return Outcome.NOT_IN_OWN_FOLDER
    if not all(_named_with(book["audible_id"], name) for name in (os.path.basename(old_dir), _stem(file_path))):
        return Outcome.NO_ID_IN_NAME
    if new_dir == old_dir:
        return Outcome.IN_PLACE
    if os.path.lexists(new_dir) or inside(old_dir, new_dir):
        return Outcome.TARGET_EXISTS
    return Outcome.MOVE


def _named_with(asin: str, name: str) -> bool:
    match = ASIN_SUFFIX.search(name)
    return bool(match) and match.group(1) == asin


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def prune_empty(directory: str, root: str) -> None:
    """Remove directory, and each parent that is left empty, up to (not including) root."""
    while inside(root, directory):
        try:
            os.rmdir(directory)
        except OSError:
            return
        directory = os.path.dirname(directory)


class LibraryMoveService:
    def __init__(self, db: Database, config: Config, library: LibraryService):
        self._db = db
        self._config = config
        self._library = library
        self._busy = threading.Lock()

    def preview(self, naming) -> dict[str, Any]:
        """What moving to this layout would do, without touching anything."""
        return self._summary(self._plans(naming))

    def move(self, naming) -> dict[str, Any]:
        """Move every book that can safely move to this layout."""
        if not self._busy.acquire(blocking=False):
            raise MoveInProgress("books are already being moved")
        try:
            plans = [self._move_one(plan) if plan.outcome == Outcome.MOVE else plan for plan in self._plans(naming)]
        finally:
            self._busy.release()
        for plan in plans:
            if plan.outcome == Outcome.MOVE:
                self._library.publish_book(plan.book_id)
        summary = self._summary(plans)
        summary["moved"] = summary.pop("to_move")
        return summary

    # --- planning ----------------------------------------------------------------------------

    def _plans(self, naming) -> list[MovePlan]:
        output_dir = os.path.abspath(self._config.output_dir)
        with self._db.session() as s:
            books = books_repo.downloaded_files(s)
            downloading = {b["book_id"] for b in books if downloads_repo.is_downloading(s, b["book_id"])}
        return [self._plan(book, naming, output_dir, book["book_id"] in downloading) for book in books]

    def _plan(self, book: dict[str, Any], naming, output_dir: str, downloading: bool) -> MovePlan:
        book = {**book, "file_path": os.path.abspath(book["file_path"])}
        names = FilenameData(**naming_data(self._library.book_meta(book["book_id"])))
        new_dir = book_directory(output_dir, naming, names)
        outcome = judge(book, new_dir, output_dir, downloading)
        return MovePlan(book["book_id"], book["title"], outcome, book["file_path"], os.path.dirname(book["file_path"]),
                        new_dir)

    # --- moving ------------------------------------------------------------------------------

    def _move_one(self, plan: MovePlan) -> MovePlan:
        output_dir = os.path.abspath(self._config.output_dir)
        try:
            os.makedirs(os.path.dirname(plan.new_dir), exist_ok=True)
            os.rename(plan.old_dir, plan.new_dir)
        except OSError as e:
            log.warning("move book %s: %s", plan.book_id, e)
            prune_empty(os.path.dirname(plan.new_dir), output_dir)
            plan.outcome = Outcome.FAILED
            return plan
        try:
            self._remember(plan)
        except Exception:
            log.exception("move book %s: could not save the new path; moving it back", plan.book_id)
            os.rename(plan.new_dir, plan.old_dir)
            prune_empty(os.path.dirname(plan.new_dir), output_dir)
            plan.outcome = Outcome.FAILED
            return plan
        prune_empty(os.path.dirname(plan.old_dir), output_dir)
        return plan

    def _remember(self, plan: MovePlan) -> None:
        with self._db.session() as s:
            books_repo.set_file_path(s, plan.book_id, os.path.join(plan.new_dir, os.path.basename(plan.file_path)))
            downloads_repo.move_folder(s, plan.old_dir, plan.new_dir)

    # --- answering ---------------------------------------------------------------------------

    def _summary(self, plans: list[MovePlan]) -> dict[str, Any]:
        output_dir = os.path.abspath(self._config.output_dir)
        moving = [p for p in plans if p.outcome == Outcome.MOVE]
        skipped = [p for p in plans if p.outcome in REASONS]
        return {
            "to_move": len(moving),
            "in_place": sum(p.outcome == Outcome.IN_PLACE for p in plans),
            "skipped_total": len(skipped),
            "skipped": [{"book_id": p.book_id, "title": p.title, "reason": REASONS[p.outcome]}
                        for p in skipped[:SKIPPED_SHOWN]],
            "examples": [{"from": os.path.relpath(p.old_dir, output_dir), "to": os.path.relpath(p.new_dir, output_dir)}
                         for p in moving[:EXAMPLE_COUNT]],
        }
