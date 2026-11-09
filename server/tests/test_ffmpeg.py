from app.audible_api.content import DownloadInfo
from app.jobs.chapters import chapter_path, parse_chapters
from app.jobs.ffmpeg import chapter_args, decrypt_args

import pytest


def pair(args, key):
    return args[args.index(key) + 1]


def test_m4b_aaxc_copies_audio():
    args = decrypt_args(DownloadInfo("u", "c", "aaxc", key="abc", iv="def"), "/tmp/in.aaxc", "/out/b.m4b", "m4b")
    assert (pair(args, "-audible_key"), pair(args, "-audible_iv"), pair(args, "-c:a")) == ("abc", "def", "copy")
    assert args[-1] == "/out/b.m4b" and "-map_chapters" not in args


def test_mp3_reencodes():
    args = decrypt_args(DownloadInfo("u", "c", "aax", activation_bytes="deadbeef"), "/tmp/in.aax", "/out/b.mp3", "mp3")
    assert pair(args, "-activation_bytes") == "deadbeef"
    assert (pair(args, "-c:a"), pair(args, "-q:a")) == ("libmp3lame", "2")


def test_chapters_file_is_second_input_after_decryption_options():
    args = decrypt_args(DownloadInfo("u", "c", "aaxc", key="k", iv="i"), "/tmp/in.aaxc", "/out/b.m4b", "m4b",
                        "/tmp/ch.ffmetadata")
    assert args.index("-audible_key") < args.index("/tmp/in.aaxc") < args.index("/tmp/ch.ffmetadata")
    assert (pair(args, "-map"), pair(args, "-map_metadata"), pair(args, "-map_chapters")) == ("0:a", "0", "1")


def test_chapter_args():
    assert chapter_args("d.m4b", "c.m4b", 0, 3723.456) == [
        "ffmpeg", "-y", "-ss", "0.000000", "-to", "3723.456000", "-i", "d.m4b", "-c", "copy", "c.m4b"]


FFPROBE = """{"chapters": [
  {"id": 0, "start_time": "0.000000", "end_time": "3723.456000", "tags": {"title": "Opening Credits"}},
  {"id": 1, "start_time": "3723.456000", "end_time": "7456.000000", "tags": {"title": "Chapter 1"}},
  {"id": 2, "start_time": "7456.000000", "end_time": "10000.000000", "tags": {}}
]}"""


def test_parse_chapters():
    chapters = parse_chapters(FFPROBE)
    assert [c.title for c in chapters] == ["Opening Credits", "Chapter 1", ""]
    assert chapters[1].start_sec == 3723.456
    assert parse_chapters('{"chapters": []}') == []
    with pytest.raises(ValueError):
        parse_chapters("not json")


def test_chapter_path():
    assert chapter_path("/out", "Book", 0, "Intro: Part 1") == "/out/Book - 01 - Intro_ Part 1"
    assert chapter_path("/out", "Book", 4, "") == "/out/Book - 05 - Chapter_05"


def test_cover_is_embedded_as_attached_picture():
    info = DownloadInfo("u", "c", "aaxc", key="k", iv="i")
    args = decrypt_args(info, "/tmp/in.aaxc", "/out/b.m4b", "m4b", "/tmp/ch.ffmetadata", "/tmp/cover.jpg")
    assert args.index("/tmp/in.aaxc") < args.index("/tmp/ch.ffmetadata") < args.index("/tmp/cover.jpg")
    assert pair(args, "-map_chapters") == "1"
    assert [args[i + 1] for i, a in enumerate(args) if a == "-map"] == ["0:a", "2:v"]
    assert (pair(args, "-c:v"), pair(args, "-disposition:v:0")) == ("copy", "attached_pic")
    assert "-vn" not in args


def test_cover_without_chapters_and_mp3_uses_id3v23():
    info = DownloadInfo("u", "c", "aax", activation_bytes="ab")
    args = decrypt_args(info, "/tmp/in.aax", "/out/b.mp3", "mp3", cover_file="/tmp/cover.jpg")
    assert [args[i + 1] for i, a in enumerate(args) if a == "-map"] == ["0:a", "1:v"]
    assert pair(args, "-id3v2_version") == "3"
    assert "-map_chapters" not in args


def test_no_cover_drops_video():
    args = decrypt_args(DownloadInfo("u", "c", "aax", activation_bytes="ab"), "/tmp/in.aax", "/out/b.m4b", "m4b")
    assert "-vn" in args and "-disposition:v:0" not in args
