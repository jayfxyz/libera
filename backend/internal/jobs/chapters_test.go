package jobs

import (
	"context"
	"strings"
	"testing"
)

var sampleFFprobeOutput = []byte(`{
  "chapters": [
    {
      "id": 0,
      "start_time": "0.000000",
      "end_time": "3723.456000",
      "tags": {"title": "Opening Credits"}
    },
    {
      "id": 1,
      "start_time": "3723.456000",
      "end_time": "7456.000000",
      "tags": {"title": "Chapter 1"}
    },
    {
      "id": 2,
      "start_time": "7456.000000",
      "end_time": "10000.000000",
      "tags": {}
    }
  ]
}`)

func TestParseChapters_Valid(t *testing.T) {
	chapters, err := parseChapters(sampleFFprobeOutput)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(chapters) != 3 {
		t.Fatalf("want 3 chapters, got %d", len(chapters))
	}
	if chapters[0].Title != "Opening Credits" {
		t.Errorf("ch[0].Title = %q", chapters[0].Title)
	}
	if chapters[2].Title != "" {
		t.Errorf("ch[2].Title should be empty for missing tag, got %q", chapters[2].Title)
	}
	if chapters[1].StartSec != 3723.456 {
		t.Errorf("ch[1].StartSec = %v", chapters[1].StartSec)
	}
}

func TestParseChapters_Empty(t *testing.T) {
	chapters, err := parseChapters([]byte(`{"chapters":[]}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(chapters) != 0 {
		t.Errorf("want 0 chapters, got %d", len(chapters))
	}
}

func TestParseChapters_Invalid(t *testing.T) {
	_, err := parseChapters([]byte(`not json`))
	if err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestBuildChapterCmd_Arguments(t *testing.T) {
	ctx := context.Background()
	cmd := buildChapterCmd(ctx, "decrypted.m4b", "ch01.m4b", 0, 3723.456)
	args := strings.Join(cmd.Args, " ")

	for _, want := range []string{"-ss", "0.000000", "-to", "3723.456000", "-i", "decrypted.m4b", "-c", "copy", "ch01.m4b"} {
		if !strings.Contains(args, want) {
			t.Errorf("expected %q in args: %s", want, args)
		}
	}
}
