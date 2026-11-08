import copy
import json

from app.jobs.outline import OutlineChapter, build_outline, cue_sheet, ffmetadata, write_outline_files

# Shape from a real title: short "Part" headings with nested chapters, a long
# parent that stays a chapter of its own, and a zero-length heading.
SAMPLE = {
    "runtime_length_ms": 100_000,
    "chapters": [
        {"title": "Opening Credits", "start_offset_ms": 0, "length_ms": 5_000},
        {"title": "Part One", "start_offset_ms": 5_000, "length_ms": 3_000, "chapters": [
            {"title": "Chapter 1", "start_offset_ms": 8_000, "length_ms": 20_000},
            {"title": "Chapter 2", "start_offset_ms": 28_000, "length_ms": 20_000},
        ]},
        {"title": "Part Two", "start_offset_ms": 48_000, "length_ms": 12_000, "chapters": [
            {"title": "Chapter 3", "start_offset_ms": 60_000, "length_ms": 30_000},
        ]},
        {"title": "Part Three", "start_offset_ms": 90_000, "length_ms": 0, "chapters": [
            {"title": "Chapter 4", "start_offset_ms": 90_000, "length_ms": 9_000},
        ]},
    ],
}


def test_build_outline_flattens_nested_chapters():
    original = copy.deepcopy(SAMPLE)
    assert build_outline(SAMPLE) == [
        OutlineChapter("Opening Credits", 0, 5_000),
        OutlineChapter("Part One: Chapter 1", 5_000, 28_000),  # short heading folded in
        OutlineChapter("Part One: Chapter 2", 28_000, 48_000),
        OutlineChapter("Part Two", 48_000, 60_000),  # long heading kept
        OutlineChapter("Part Two: Chapter 3", 60_000, 90_000),
        OutlineChapter("Part Three: Chapter 4", 90_000, 100_000),  # runs to the runtime
    ]
    assert SAMPLE == original  # input untouched


def test_build_outline_drops_empty_and_handles_none():
    assert build_outline(None) == []
    got = build_outline({"chapters": [{"title": "A", "start_offset_ms": 0, "length_ms": 0},
                                      {"title": "B", "start_offset_ms": 0, "length_ms": 1_000}]})
    assert got == [OutlineChapter("B", 0, 1_000)]


def test_ffmetadata_escapes_special_characters():
    got = ffmetadata([OutlineChapter("Intro", 0, 1_500), OutlineChapter("Rule 1 = Stand; #1 \\ up", 1_500, 9_000)])
    assert got == (";FFMETADATA1\n"
                   "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1500\ntitle=Intro\n"
                   "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=1500\nEND=9000\ntitle=Rule 1 \\= Stand\\; \\#1 \\\\ up\n")


def test_cue_sheet():
    got = cue_sheet("My Book.m4b", [
        OutlineChapter("Opening Credits", 0, 16_600),
        OutlineChapter('Say "Hi"', 16_600, 6_000_000),
        OutlineChapter("Late", 6_062_500, 6_100_000),  # 101 min 2.5 s
    ])
    assert got == ('FILE "My Book.m4b" MP3\n'
                   'TRACK 1 AUDIO\n  TITLE "Opening Credits"\n  INDEX 01 00:00:00\n'
                   "TRACK 2 AUDIO\n  TITLE \"Say 'Hi'\"\n  INDEX 01 00:16:45\n"
                   'TRACK 3 AUDIO\n  TITLE "Late"\n  INDEX 01 101:02:37\n')


def test_write_outline_files(tmp_path):
    audio = tmp_path / "Book.m4b"
    chapters = build_outline(SAMPLE)
    write_outline_files(str(audio), "B0001", "Book", SAMPLE, chapters)
    assert (tmp_path / "Book.cue").read_text().startswith('FILE "Book.m4b" MP3')
    doc = json.loads((tmp_path / "Book.chapters.json").read_text())
    assert (doc["asin"], doc["audio_file"], doc["runtime_ms"]) == ("B0001", "Book.m4b", 100_000)
    assert len(doc["chapters"]) == len(chapters)
    assert len(doc["audible_chapter_info"]["chapters"][1]["chapters"]) == 2  # nested outline kept
