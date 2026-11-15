"""The real download pipeline (fetch, then decrypt with real ffmpeg), run
through both tasks; only Audible and HTTP are faked."""

import asyncio
import json
import os
import shutil
import subprocess

import httpx
import pytest

from app.audible_api.content import ContentError, DownloadInfo
from app.jobs import download
from app.jobs.download import read_fetched_bundle, tiny_download_error
from app.services.library import LibraryService
from app.services.downloads import DownloadEvents, DownloadsService
from app.services.task_queue import TaskQueueService
from app.services.task_worker import TaskWorkerService
from app.tasks.downloads import DownloadHandlers, Pipeline
from app.tasks.signals import TaskSignals
from tests.conftest import add_account, make_book, import_books

CHAPTERS = {
    "runtime_length_ms": 6000,
    "chapters": [
        {"title": "Opening Credits", "start_offset_ms": 0, "length_ms": 1000},
        {"title": "Part One", "start_offset_ms": 1000, "length_ms": 500, "chapters": [
            {"title": "Chapter 1", "start_offset_ms": 1500, "length_ms": 4500}]},
    ],
}


class FakeAudible:
    def __init__(self, source: str, info: DownloadInfo | None = None, error: str = "",
                 pdf: bytes | None = b"%PDF-1.4 test"):
        self.source, self.error, self.pdf = source, error, pdf
        self.info = info or DownloadInfo(download_url=source, codec="LC_64", format="aax", activation_bytes="deadbeef")
        self.calls = {"license": 0, "pdf": 0}

    async def get_download_info(self, account_id, asin):
        self.calls["license"] += 1
        if self.error:
            raise ContentError(self.error)
        return self.info

    async def get_chapter_info(self, account_id, asin):
        return CHAPTERS

    async def get_pdf(self, account_id, asin):
        self.calls["pdf"] += 1
        return self.pdf


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


class Downloader:
    """The download services as the app wires them, with the real pipeline."""

    def __init__(self, db, config, audible):
        self.db = db
        signals = TaskSignals()
        self.worker = TaskWorkerService(db, signals, workers=1)
        self.svc = DownloadsService(db, config, TaskQueueService(db, signals), DownloadEvents(), audible,
                                    LibraryService(db, config))
        DownloadHandlers(self.svc, Pipeline(audible)).register(self.worker)
        self.worker.start()
        self.svc.start()

    async def run(self, book_id: int, **opts) -> dict:
        return await self.wait(self.svc.enqueue(book_id, **opts))

    async def wait(self, download_id: str) -> dict:
        for _ in range(600):
            view = next(v for v in self.svc.list() if v["job_id"] == download_id)
            settled = self.db.scalar("SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'processing')") == 0
            if view["status"] in ("done", "failed") and settled:  # the last step and its cleanup are over
                return view
            await asyncio.sleep(0.05)
        raise AssertionError(f"download did not finish: {view}")


@pytest.fixture
async def make_downloader(db, config):
    made = []

    def make(audible):
        made.append(Downloader(db, config, audible))
        return made[-1]

    yield make
    for d in made:
        await d.worker.stop()


@pytest.fixture
def book_id(db):
    add_account(db)
    import_books(db, 1, [make_book("B0001", title="The Book", authors=["Jane Author"])])
    return db.scalar("SELECT id FROM books")


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
async def test_download_writes_book_folder_with_chapters_cover_and_pdf(db, config, book_id, source_audio,
                                                                       cover_jpg, make_downloader, fmt):
    info = DownloadInfo(source_audio, "LC_64", "aax", activation_bytes="deadbeef", cover_url=cover_jpg)
    view = await make_downloader(FakeAudible(source_audio, info)).run(book_id, format=fmt)

    book_dir = os.path.join(config.output_dir, "Jane Author - The Book")
    assert view["status"] == "done", view
    assert view["message"] == os.path.join(book_dir, f"The Book.{fmt}")
    assert os.listdir(config.output_dir) == ["Jane Author - The Book"]  # work folder cleaned up
    roles = {f"The Book.{fmt}": "audio", "The Book.cue": "metadata", "The Book.chapters.json": "metadata",
             "The Book.pdf": "pdf", "cover.jpg": "cover"}
    assert sorted(os.listdir(book_dir)) == sorted(roles)
    # The manifest lists every file with its role and size.
    assert {f["name"]: f["role"] for f in view["files"]} == roles
    assert all(f["size_bytes"] == os.path.getsize(os.path.join(book_dir, f["name"])) for f in view["files"])
    assert probe_chapters(os.path.join(book_dir, f"The Book.{fmt}")) == [
        ("Opening Credits", 0.0), ("Part One: Chapter 1", 1.0)]
    assert probe_cover(os.path.join(book_dir, f"The Book.{fmt}")) == [("mjpeg", 64)]
    with open(os.path.join(book_dir, "cover.jpg"), "rb") as a, open(cover_jpg, "rb") as b:
        assert a.read() == b.read()
    lib = db.query_one("SELECT liberation_status, last_format FROM library_books WHERE book_id = ?", (book_id,))
    assert (lib["liberation_status"], lib["last_format"]) == ("liberated", fmt)


async def test_missing_or_bad_cover_does_not_fail_the_download(config, book_id, tmp_path, source_audio,
                                                               make_downloader):
    not_jpeg = tmp_path / "cover.png"
    not_jpeg.write_bytes(b"\x89PNG not a jpeg")
    for cover_url in (str(not_jpeg), ""):
        info = DownloadInfo(source_audio, "LC_64", "aax", activation_bytes="ab", cover_url=cover_url)
        view = await make_downloader(FakeAudible(source_audio, info)).run(book_id)
        assert view["status"] == "done", view
        audio = os.path.join(config.output_dir, "Jane Author - The Book", "The Book.m4b")
        assert probe_cover(audio) == []
        assert not os.path.exists(os.path.join(os.path.dirname(audio), "cover.jpg"))


async def test_split_chapters(config, book_id, source_audio, make_downloader):
    view = await make_downloader(FakeAudible(source_audio)).run(book_id, split_chapters=True)
    assert view["status"] == "done", view
    chapters = sorted(f["name"] for f in view["files"] if f["role"] == "chapter")
    assert chapters == ["The Book - 01 - Opening Credits.m4b", "The Book - 02 - Part One_ Chapter 1.m4b"]
    assert set(chapters) <= set(os.listdir(os.path.join(config.output_dir, "Jane Author - The Book")))


async def test_license_denial_explains_tiny_download(db, config, book_id, tmp_path, monkeypatch, make_downloader):
    body = tmp_path / "body.txt"
    body.write_text("No Library Record Found for user.")
    info = DownloadInfo(str(body), "c", "aax", activation_bytes="ab", license_denied="Audible is throttling.")
    monkeypatch.setattr(download, "MIN_AUDIOBOOK_BYTES", 1024)
    audible = FakeAudible(str(body), info)

    view = await make_downloader(audible).run(book_id)

    assert view["status"] == "failed"
    assert view["message"] == "Audible is throttling. (fallback AAX download also failed: No Library Record Found for user.)"
    assert db.scalar("SELECT liberation_status FROM library_books WHERE book_id = ?", (book_id,)) == "error"
    assert os.listdir(config.output_dir) == []  # nothing left behind
    assert audible.calls["license"] == 1  # a refusal is not retried


async def test_download_info_error(book_id, make_downloader):
    view = await make_downloader(FakeAudible("", error="Library fetch failed: 401")).run(book_id)
    assert (view["status"], view["message"]) == ("failed", "get download info: Library fetch failed: 401")


def test_tiny_download_error():
    assert tiny_download_error(33, " No Library Record Found for user.\n", "Throttled.") == \
        "Throttled. (fallback AAX download also failed: No Library Record Found for user.)"
    assert tiny_download_error(33, "oops", "") == "download returned 33 bytes (expected an audiobook file): oops"


async def test_a_missing_pdf_does_not_fail_the_download(config, book_id, source_audio, make_downloader):
    view = await make_downloader(FakeAudible(source_audio, pdf=None)).run(book_id)
    assert view["status"] == "done", view
    assert "pdf" not in {f["role"] for f in view["files"]}
    assert not os.path.exists(os.path.join(config.output_dir, "Jane Author - The Book", "The Book.pdf"))


async def test_no_pdf_is_requested_when_the_book_has_none(db, book_id, source_audio, make_downloader):
    db.execute("UPDATE books SET has_pdf = 0")
    audible = FakeAudible(source_audio)
    view = await make_downloader(audible).run(book_id)
    assert view["status"] == "done" and audible.calls["pdf"] == 0


async def test_a_failed_decrypt_is_retried_from_the_kept_download(book_id, source_audio, make_downloader,
                                                                  monkeypatch):
    real_run, failed = download.run, []

    async def ffmpeg_broken_once(args):
        if args[0] == "ffmpeg" and not failed:
            failed.append(args)
            return 1, b"", b"Invalid data found"
        return await real_run(args)

    monkeypatch.setattr(download, "run", ffmpeg_broken_once)
    audible = FakeAudible(source_audio)
    downloader = make_downloader(audible)
    view = await downloader.run(book_id)
    assert (view["status"], view["message"]) == ("failed", "ffmpeg: Invalid data found")
    assert read_fetched_bundle(downloader.svc.work_dir, view["job_id"]) is not None

    assert downloader.svc.retry(view["job_id"])
    view = await downloader.wait(view["job_id"])
    assert view["status"] == "done", view
    assert audible.calls["license"] == 1  # not downloaded again
    assert not os.path.exists(downloader.svc.work_dir)  # the bundle is gone once done


async def test_a_network_error_during_download_is_retried(book_id, source_audio, make_downloader, monkeypatch):
    copy, failures = download._stream_download, [httpx.ConnectError("connection reset")]

    async def flaky(url, dest, on_progress):
        if failures:
            raise failures.pop()
        await copy(url, dest, on_progress)

    monkeypatch.setattr(download, "_stream_download", flaky)
    audible = FakeAudible(source_audio)
    view = await make_downloader(audible).run(book_id)
    assert view["status"] == "done", view
    assert audible.calls["license"] == 2  # the second attempt asked for the license again
