package jobs

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/web-libation/backend/internal/audible"
)

// Shape taken from a real title: short "Part" headings with nested chapters,
// plus a long parent that must stay a chapter of its own.
func sampleChapterInfo() *audible.ChapterInfo {
	return &audible.ChapterInfo{
		RuntimeLengthMs: 100_000,
		Chapters: []audible.AudibleChapter{
			{Title: "Opening Credits", StartOffsetMs: 0, LengthMs: 5_000},
			{Title: "Part One", StartOffsetMs: 5_000, LengthMs: 3_000, Chapters: []audible.AudibleChapter{
				{Title: "Chapter 1", StartOffsetMs: 8_000, LengthMs: 20_000},
				{Title: "Chapter 2", StartOffsetMs: 28_000, LengthMs: 20_000},
			}},
			{Title: "Part Two", StartOffsetMs: 48_000, LengthMs: 12_000, Chapters: []audible.AudibleChapter{
				{Title: "Chapter 3", StartOffsetMs: 60_000, LengthMs: 30_000},
			}},
			// Zero-length heading, as Audible returns for some parts.
			{Title: "Part Three", StartOffsetMs: 90_000, LengthMs: 0, Chapters: []audible.AudibleChapter{
				{Title: "Chapter 4", StartOffsetMs: 90_000, LengthMs: 9_000},
			}},
		},
	}
}

func TestBuildOutline_FlattensNestedChapters(t *testing.T) {
	info := sampleChapterInfo()
	got := buildOutline(info)
	want := []OutlineChapter{
		{"Opening Credits", 0, 5_000},
		// short heading folded into its first child
		{"Part One: Chapter 1", 5_000, 28_000},
		{"Part One: Chapter 2", 28_000, 48_000},
		// long heading kept as its own chapter
		{"Part Two", 48_000, 60_000},
		{"Part Two: Chapter 3", 60_000, 90_000},
		// last chapter runs to the book's runtime
		{"Part Three: Chapter 4", 90_000, 100_000},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("outline mismatch\n got: %+v\nwant: %+v", got, want)
	}
	// input tree untouched
	if info.Chapters[1].Chapters[0].Title != "Chapter 1" || info.Chapters[1].Chapters[0].StartOffsetMs != 8_000 {
		t.Errorf("buildOutline modified its input: %+v", info.Chapters[1].Chapters[0])
	}
}

func TestBuildOutline_DropsEmptyAndHandlesNil(t *testing.T) {
	if buildOutline(nil) != nil {
		t.Error("nil info should give nil outline")
	}
	got := buildOutline(&audible.ChapterInfo{Chapters: []audible.AudibleChapter{
		{Title: "A", StartOffsetMs: 0, LengthMs: 0},
		{Title: "B", StartOffsetMs: 0, LengthMs: 1_000},
	}})
	if len(got) != 1 || got[0].Title != "B" || got[0].EndMs != 1_000 {
		t.Errorf("expected only B, got %+v", got)
	}
}

func TestFFMetadata(t *testing.T) {
	got := ffmetadata([]OutlineChapter{
		{"Intro", 0, 1_500},
		{"Rule 1 = Stand; #1 \\ up", 1_500, 9_000},
	})
	want := ";FFMETADATA1\n" +
		"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1500\ntitle=Intro\n" +
		"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=1500\nEND=9000\ntitle=Rule 1 \\= Stand\\; \\#1 \\\\ up\n"
	if got != want {
		t.Errorf("ffmetadata mismatch\n got: %q\nwant: %q", got, want)
	}
}

func TestCueSheet(t *testing.T) {
	got := cueSheet("My Book.m4b", []OutlineChapter{
		{"Opening Credits", 0, 16_600},
		{`Say "Hi"`, 16_600, 6_000_000},
		{"Late", 6_062_500, 6_100_000}, // 101 min, 2.5 s
	})
	want := `FILE "My Book.m4b" MP3
TRACK 1 AUDIO
  TITLE "Opening Credits"
  INDEX 01 00:00:00
TRACK 2 AUDIO
  TITLE "Say 'Hi'"
  INDEX 01 00:16:45
TRACK 3 AUDIO
  TITLE "Late"
  INDEX 01 101:02:37
`
	if got != want {
		t.Errorf("cue mismatch\n got:\n%s\nwant:\n%s", got, want)
	}
}

func TestWriteOutlineFiles(t *testing.T) {
	dir := t.TempDir()
	audio := filepath.Join(dir, "Book.m4b")
	info := sampleChapterInfo()
	chapters := buildOutline(info)

	if err := writeOutlineFiles(audio, DownloadJob{AudibleID: "B0001", Title: "Book"}, info, chapters); err != nil {
		t.Fatal(err)
	}

	cue, err := os.ReadFile(filepath.Join(dir, "Book.cue"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(string(cue), `FILE "Book.m4b" MP3`) {
		t.Errorf("cue should reference the audio file, got %q", string(cue))
	}

	raw, err := os.ReadFile(filepath.Join(dir, "Book.chapters.json"))
	if err != nil {
		t.Fatal(err)
	}
	var doc outlineDoc
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	if doc.ASIN != "B0001" || doc.AudioFile != "Book.m4b" || len(doc.Chapters) != len(chapters) {
		t.Errorf("unexpected doc: %+v", doc)
	}
	if doc.Audible == nil || len(doc.Audible.Chapters[1].Chapters) != 2 {
		t.Error("json should keep Audible's nested outline")
	}
}
