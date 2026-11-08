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

func TestBookDirectory(t *testing.T) {
	data := FilenameData{Title: "The Name of the Wind", Authors: "Patrick Rothfuss"}

	if got := bookDirectory("/audiobooks", "{author} - {title}", data); got != "/audiobooks/Patrick Rothfuss - The Name of the Wind" {
		t.Errorf("default template: got %q", got)
	}
	if got := bookDirectory("/audiobooks", "", data); got != "/audiobooks" {
		t.Errorf("empty template should use output dir, got %q", got)
	}
	if got := bookDirectory("/audiobooks", "  ", data); got != "/audiobooks" {
		t.Errorf("blank template should use output dir, got %q", got)
	}
	// Missing author: no dangling separator. A "/" in metadata must not create
	// a nested folder.
	got := bookDirectory("/audiobooks", "{author} - {title}", FilenameData{Title: "AC/DC: A Story"})
	if got != "/audiobooks/AC_DC_ A Story" {
		t.Errorf("unsafe/missing values: got %q", got)
	}
}

func TestTinyDownloadError(t *testing.T) {
	got := tinyDownloadError(33, " No Library Record Found for user.\n", "Audible is temporarily refusing download licenses for this account.")
	want := "Audible is temporarily refusing download licenses for this account. (fallback AAX download also failed: No Library Record Found for user.)"
	if got != want {
		t.Errorf("with license reason:\n got %q\nwant %q", got, want)
	}
	if got := tinyDownloadError(33, "oops", ""); got != "download returned 33 bytes (expected an audiobook file): oops" {
		t.Errorf("without license reason: got %q", got)
	}
}
