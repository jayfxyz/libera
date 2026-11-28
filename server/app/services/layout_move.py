"""Moving downloaded books to another folder layout.

A book's folder moves only when Libera can be sure it holds that one book. Either the folder and the audio file
both end in the book's own Audible ID (how Libera names things now), or the folder is a book folder from an older
version: no other book's recorded file is inside it and its only audio is this book's. Anything else is left
where it is and reported.

A book from an older version also gets its files renamed to include its ID, like a new download."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..config import Config
from ..db import Database
from ..jobs.filename import FilenameData, book_directory, book_file_name
from ..naming import ASIN_SUFFIX
from ..repositories import books as books_repo
from ..repositories import downloads as downloads_repo
from .library import AUDIO_EXTENSIONS, LibraryService, naming_data

log = logging.getLogger(__name__)

EXAMPLE_COUNT = 3
SKIPPED_SHOWN = 20


class Outcome(StrEnum):
    MOVE = "move"
    IN_PLACE = "in_place"
    SHARED_FOLDER = "shared_folder"
    FILE_MISSING = "file_missing"
    NOT_IN_OWN_FOLDER = "not_in_own_folder"
    TARGET_EXISTS = "target_exists"
    NESTED = "nested"
    DOWNLOADING = "downloading"
    FAILED = "failed"


REASONS = {
    Outcome.SHARED_FOLDER: "Its folder holds other books or files",
    Outcome.FILE_MISSING: "The file is not on disk",
    Outcome.NOT_IN_OWN_FOLDER: "It is not in a folder of its own inside the output folder",
    Outcome.TARGET_EXISTS: "A folder with the new name already exists",
    Outcome.NESTED: "The new folder would be inside the old one",
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
    old_stem: str
    new_stem: str  # the files are renamed to this when it differs from old_stem (older versions had no ID)


def inside(root: str, path: str) -> bool:
    return os.path.commonpath([root, path]) == root and path != root


def judge(book: dict[str, Any], new_dir: str, output_dir: str, other_files: set[str], downloading: bool) -> Outcome:
    """What can safely be done with one book's folder. other_files: where the other books' files are."""
    file_path = book["file_path"]
    old_dir = os.path.dirname(file_path)
    if downloading:
        return Outcome.DOWNLOADING
    if not os.path.isfile(file_path):
        return Outcome.FILE_MISSING
    if not inside(output_dir, old_dir) or os.path.islink(old_dir):
        return Outcome.NOT_IN_OWN_FOLDER
    if not named_with_id(book["audible_id"], file_path) and not holds_only_this_book(file_path, other_files):
        return Outcome.SHARED_FOLDER
    if new_dir == old_dir:
        return Outcome.IN_PLACE
    if inside(old_dir, new_dir):
        return Outcome.NESTED
    if os.path.lexists(new_dir):
        return Outcome.TARGET_EXISTS
    return Outcome.MOVE


def named_with_id(asin: str, file_path: str) -> bool:
    """The folder and the audio file both end in the book's own ID."""
    names = (os.path.basename(os.path.dirname(file_path)), os.path.splitext(os.path.basename(file_path))[0])
    return all((match := ASIN_SUFFIX.search(name)) and match.group(1) == asin for name in names)


def belongs_to_book(name: str, stem: str) -> bool:
    """A file in a book's folder that goes with the audio file: its sidecars and its chapter files."""
    return name.startswith((f"{stem}.", f"{stem} - "))


def holds_only_this_book(file_path: str, other_files: set[str]) -> bool:
    """The book's folder has no other book's file in it, and no audio that is not this book's."""
    folder, stem = os.path.dirname(file_path), os.path.splitext(os.path.basename(file_path))[0]
    if any(other.startswith(folder + os.sep) for other in other_files):
        return False
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            is_audio = name.lower().endswith(AUDIO_EXTENSIONS)
            if is_audio and not (dirpath == folder and belongs_to_book(name, stem)):
                return False
    return True


def prune_empty(directory: str, root: str) -> None:
    """Remove directory, and each parent that is left empty, up to (not including) root."""
    while inside(root, directory):
        try:
            os.rmdir(directory)
        except OSError:
            return
        directory = os.path.dirname(directory)


def renamed(name: str, old_stem: str, new_stem: str) -> str:
    return new_stem + name[len(old_stem):]


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
            books = [{**b, "file_path": os.path.abspath(b["file_path"])} for b in books_repo.downloaded_files(s)]
            downloading = {b["book_id"] for b in books if downloads_repo.is_downloading(s, b["book_id"])}
        files = {b["book_id"]: b["file_path"] for b in books}
        return [self._plan(book, naming, output_dir, {p for i, p in files.items() if i != book["book_id"]},
                           book["book_id"] in downloading) for book in books]

    def _plan(self, book: dict[str, Any], naming, output_dir: str, other_files: set[str], downloading: bool) -> MovePlan:
        names = FilenameData(**naming_data(self._library.book_meta(book["book_id"])))
        new_dir = book_directory(output_dir, naming, names)
        outcome = judge(book, new_dir, output_dir, other_files, downloading)
        old_stem = os.path.splitext(os.path.basename(book["file_path"]))[0]
        new_stem = old_stem if named_with_id(book["audible_id"], book["file_path"]) else book_file_name(names)
        return MovePlan(book["book_id"], book["title"], outcome, book["file_path"], os.path.dirname(book["file_path"]),
                        new_dir, old_stem, new_stem)

    # --- moving ------------------------------------------------------------------------------

    def _move_one(self, plan: MovePlan) -> MovePlan:
        output_dir = os.path.abspath(self._config.output_dir)
        done: list[tuple[str, str]] = []  # (from, to), in the order done
        try:
            os.makedirs(os.path.dirname(plan.new_dir), exist_ok=True)
            os.rename(plan.old_dir, plan.new_dir)
            done.append((plan.old_dir, plan.new_dir))
            renames = self._rename_files(plan, done)
            self._remember(plan, renames)
        except Exception:
            log.exception("move book %s: undoing it", plan.book_id)
            self._undo(done)
            prune_empty(os.path.dirname(plan.new_dir), output_dir)
            plan.outcome = Outcome.FAILED
            return plan
        prune_empty(os.path.dirname(plan.old_dir), output_dir)
        return plan

    def _rename_files(self, plan: MovePlan, done: list[tuple[str, str]]) -> dict[str, str]:
        """Rename the book's files in its new folder to the new stem. Returns old name → new name."""
        renames: dict[str, str] = {}
        if plan.new_stem == plan.old_stem:
            return renames
        for name in sorted(os.listdir(plan.new_dir)):
            target = renamed(name, plan.old_stem, plan.new_stem)
            if belongs_to_book(name, plan.old_stem) and not os.path.lexists(os.path.join(plan.new_dir, target)):
                os.rename(os.path.join(plan.new_dir, name), os.path.join(plan.new_dir, target))
                done.append((os.path.join(plan.new_dir, name), os.path.join(plan.new_dir, target)))
                renames[name] = target
        return renames

    @staticmethod
    def _undo(done: list[tuple[str, str]]) -> None:
        for source, target in reversed(done):
            try:
                os.rename(target, source)
            except OSError:
                log.exception("could not put %s back as %s", target, source)

    def _remember(self, plan: MovePlan, renames: dict[str, str]) -> None:
        audio = os.path.basename(plan.file_path)
        with self._db.session() as s:
            books_repo.set_file_path(s, plan.book_id, os.path.join(plan.new_dir, renames.get(audio, audio)))
            downloads_repo.move_folder(s, plan.old_dir, plan.new_dir)
            downloads_repo.rename_files(s, plan.new_dir, renames, plan.old_stem, plan.new_stem)

    # --- answering ---------------------------------------------------------------------------

    def _summary(self, plans: list[MovePlan]) -> dict[str, Any]:
        output_dir = os.path.abspath(self._config.output_dir)
        moving = [p for p in plans if p.outcome == Outcome.MOVE]
        skipped = [p for p in plans if p.outcome in REASONS]
        return {
            "to_move": len(moving),
            "to_rename": sum(p.new_stem != p.old_stem for p in moving),
            "in_place": sum(p.outcome == Outcome.IN_PLACE for p in plans),
            "skipped_total": len(skipped),
            "skipped": [{"book_id": p.book_id, "title": p.title, "reason": REASONS[p.outcome]}
                        for p in skipped[:SKIPPED_SHOWN]],
            "examples": [{"from": os.path.relpath(p.old_dir, output_dir), "to": os.path.relpath(p.new_dir, output_dir)}
                         for p in moving[:EXAMPLE_COUNT]],
        }
