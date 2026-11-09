"""A download job end to end with real ffmpeg; only Audible is faked."""

import asyncio
import json
import os
import shutil
import subprocess

import pytest

from app import library
from app.audible_api.content import ContentError, DownloadInfo
from app.jobs import download
from app.jobs.download import make_runner, tiny_download_error
from app.jobs.queue import DownloadJob, DownloadQueue
from tests.conftest import add_account, make_book

CHAPTERS = {
    "runtime_length_ms": 6000,
    "chapters": [
        {"title": "Opening Credits", "start_offset_ms": 0, "length_ms": 1000},
        {"title": "Part One", "start_offset_ms": 1000, "length_ms": 500, "chapters": [
            {"title": "Chapter 1", "start_offset_ms": 1500, "length_ms": 4500}]},
    ],
}


class FakeAudible:
    def __init__(self, source: str, info: DownloadInfo | None = None, error: str = ""):
        self.source, self.error = source, error
        self.info = info or DownloadInfo(download_url=source, codec="LC_64", format="aax", activation_bytes="deadbeef")

    async def get_download_info(self, account_id, asin):
        if self.error:
            raise ContentError(self.error)
        return self.info

    async def get_chapter_info(self, account_id, asin):
        return CHAPTERS

    async def get_pdf(self, account_id, asin):
        return b"%PDF-1.4 test"


@pytest.fixture
def source_audio(tmp_path):
    path = tmp_path / "source.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-c:a", "aac", str(path)], check=True)
    return str(path)


@pytest.fixture
def cover_jpg(tmp_path):
    path = tmp_path / "cover-source.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=teal:s=64x64", "-frames:v", "1",
                    str(path)], check=True)
    return str(path)


@pytest.fixture(autouse=True)
def local_download(monkeypatch):
    """Downloads read local files instead of URLs."""
    async def copy(url, dest, on_progress):
        on_progress(50)
        shutil.copyfile(url, dest)

    async def read(url):
        with open(url, "rb") as f:
            return f.read()

    monkeypatch.setattr(download, "_stream_download", copy)
    monkeypatch.setattr(download, "_fetch_bytes", read)
    monkeypatch.setattr(download, "MIN_AUDIOBOOK_BYTES", 1)


def make_job(output_dir: str, book_id: int, fmt: str = "m4b", **kw) -> DownloadJob:
    return DownloadJob(id=f"dl-{book_id}", book_id=book_id, audible_id="B0001", account_id=1,
                       audible_account_id="amzn1.account.TEST", title="The Book", format=fmt,
                       output_dir=output_dir, filename_template="{title}", folder_template="{author} - {title}",
                       authors="Jane Author", **kw)


async def run_job(db, audible, job):
    q = DownloadQueue(make_runner(db, audible), workers=1)
    q.start()
    q.enqueue(job)
    for _ in range(300):
        state = q.list_jobs()[0]
        if state["status"] in ("done", "error"):
            break
        await asyncio.sleep(0.05)
    await q.stop()
    return state


def probe_chapters(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", path],
                         capture_output=True, check=True).stdout
    return [(c["tags"]["title"], round(float(c["start_time"]), 1)) for c in json.loads(out)["chapters"]]


def probe_cover(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width:stream_disposition=attached_pic", "-of", "json", path],
                         capture_output=True, check=True).stdout
    return [(s["codec_name"], s["width"]) for s in json.loads(out)["streams"]
            if s["codec_type"] == "video" and s["disposition"]["attached_pic"]]


@pytest.mark.parametrize("fmt", ["m4b", "mp3"])
async def test_download_writes_book_folder_with_chapters_and_cover(db, tmp_path, source_audio, cover_jpg, fmt):
    add_account(db)
    library.import_library(db, 1, [make_book("B0001", title="The Book")])
    book_id = db.scalar("SELECT id FROM books")
    out_dir = tmp_path / "audiobooks"
    info = DownloadInfo(source_audio, "LC_64", "aax", activation_bytes="deadbeef", cover_url=cover_jpg)

    state = await run_job(db, FakeAudible(source_audio, info), make_job(str(out_dir), book_id, fmt))

    book_dir = out_dir / "Jane Author - The Book"
    assert state["status"] == "done", state
    assert state["message"] == str(book_dir / f"The Book.{fmt}")
    assert sorted(os.listdir(out_dir)) == ["Jane Author - The Book"]  # work folder cleaned up
    assert sorted(os.listdir(book_dir)) == sorted(
        [f"The Book.{fmt}", "The Book.cue", "The Book.chapters.json", "The Book.pdf", "cover.jpg"])
    assert probe_chapters(str(book_dir / f"The Book.{fmt}")) == [
        ("Opening Credits", 0.0), ("Part One: Chapter 1", 1.0)]
    assert probe_cover(str(book_dir / f"The Book.{fmt}")) == [("mjpeg", 64)]
    assert (book_dir / "cover.jpg").read_bytes() == open(cover_jpg, "rb").read()
    row = db.query_one("SELECT liberation_status, last_format FROM library_books WHERE book_id = ?", (book_id,))
    assert (row["liberation_status"], row["last_format"]) == ("liberated", fmt)


async def test_missing_cover_does_not_fail_the_job(db, tmp_path, source_audio):
    add_account(db)
    library.import_library(db, 1, [make_book("B0001", title="The Book")])
    book_id = db.scalar("SELECT id FROM books")
    info = DownloadInfo(source_audio, "LC_64", "aax", activation_bytes="ab", cover_url=str(tmp_path / "nope.jpg"))
    not_jpeg = tmp_path / "cover.png"
    not_jpeg.write_bytes(b"\x89PNG not a jpeg")

    for cover_url in (str(not_jpeg), ""):
        info.cover_url = cover_url
        state = await run_job(db, FakeAudible(source_audio, info), make_job(str(tmp_path / "out"), book_id))
        assert state["status"] == "done", state
        audio = tmp_path / "out" / "Jane Author - The Book" / "The Book.m4b"
        assert probe_cover(str(audio)) == []
        assert not (audio.parent / "cover.jpg").exists()


async def test_split_chapters(db, tmp_path, source_audio):
    add_account(db)
    library.import_library(db, 1, [make_book("B0001", title="The Book")])
    book_id = db.scalar("SELECT id FROM books")
    state = await run_job(db, FakeAudible(source_audio), make_job(str(tmp_path), book_id, split_chapters=True))
    assert state["status"] == "done", state
    files = os.listdir(tmp_path / "Jane Author - The Book")
    assert "The Book - 01 - Opening Credits.m4b" in files
    assert "The Book - 02 - Part One_ Chapter 1.m4b" in files


async def test_license_denial_explains_tiny_download(db, tmp_path, monkeypatch):
    add_account(db)
    library.import_library(db, 1, [make_book("B0001")])
    book_id = db.scalar("SELECT id FROM books")
    body = tmp_path / "body.txt"
    body.write_text("No Library Record Found for user.")
    info = DownloadInfo(str(body), "c", "aax", activation_bytes="ab", license_denied="Audible is throttling.")
    monkeypatch.setattr(download, "MIN_AUDIOBOOK_BYTES", 1024)

    state = await run_job(db, FakeAudible(str(body), info), make_job(str(tmp_path / "out"), book_id))

    assert state["status"] == "error"
    assert state["message"] == "Audible is throttling. (fallback AAX download also failed: No Library Record Found for user.)"
    assert db.scalar("SELECT liberation_status FROM library_books WHERE book_id = ?", (book_id,)) == "error"
    assert os.listdir(tmp_path / "out") == []  # nothing left behind


async def test_download_info_error(db, tmp_path):
    add_account(db)
    library.import_library(db, 1, [make_book("B0001")])
    book_id = db.scalar("SELECT id FROM books")
    state = await run_job(db, FakeAudible("", error="Library fetch failed: 401"), make_job(str(tmp_path), book_id))
    assert (state["status"], state["message"]) == ("error", "get download info: Library fetch failed: 401")


def test_tiny_download_error():
    assert tiny_download_error(33, " No Library Record Found for user.\n", "Throttled.") == \
        "Throttled. (fallback AAX download also failed: No Library Record Found for user.)"
    assert tiny_download_error(33, "oops", "") == "download returned 33 bytes (expected an audiobook file): oops"
