package jobs

import "testing"

func TestRenderFilename_DefaultTemplate(t *testing.T) {
	data := FilenameData{Title: "The Great Gatsby", Authors: "F. Scott Fitzgerald"}
	got := renderFilename("{title}", data)
	if got != "The Great Gatsby" {
		t.Errorf("got %q", got)
	}
}

func TestRenderFilename_AllTags(t *testing.T) {
	data := FilenameData{
		Title:       "Dune",
		Authors:     "Frank Herbert",
		Narrators:   "Scott Brick",
		SeriesName:  "Dune Chronicles",
		SeriesIndex: "1",
		Year:        "1965",
		Language:    "english",
		DurationH:   "21",
	}
	tmpl := "{author} - {series} {series_index} - {title} ({year}) [{narrator}]"
	got := renderFilename(tmpl, data)
	want := "Frank Herbert - Dune Chronicles 1 - Dune (1965) [Scott Brick]"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestRenderFilename_MissingTag_Omitted(t *testing.T) {
	data := FilenameData{Title: "Book"}
	got := renderFilename("{title} - {series}", data)
	// Series is empty — the " - " separating it and the tag itself should collapse.
	// We strip " - {series}" when series is empty to avoid trailing separators.
	if got == "Book -" || got == "Book - " {
		t.Errorf("trailing separator not cleaned: %q", got)
	}
}

func TestRenderFilename_UnsafeChars(t *testing.T) {
	data := FilenameData{Title: `H/G: A <Tale>`}
	got := renderFilename("{title}", data)
	// Unsafe chars must be replaced
	for _, ch := range `/<>:` {
		for _, r := range got {
			if r == ch {
				t.Errorf("unsafe char %q present in %q", ch, got)
			}
		}
	}
}

func TestRenderFilename_FallbackToTitle(t *testing.T) {
	data := FilenameData{Title: "Fallback"}
	got := renderFilename("", data)
	if got != "Fallback" {
		t.Errorf("empty template should fall back to title, got %q", got)
	}
}
