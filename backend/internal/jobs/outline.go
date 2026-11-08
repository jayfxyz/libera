package jobs

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/web-libation/backend/internal/audible"
)

// OutlineChapter is one entry in a book's flat chapter outline, in
// milliseconds from the start of the decrypted audio.
type OutlineChapter struct {
	Title   string `json:"title"`
	StartMs int64  `json:"start_ms"`
	EndMs   int64  `json:"end_ms"`
}

// nestedTitleSep joins a parent's title to its children's, e.g.
// "Part One: Chapter 1". Same separator Libation uses.
const nestedTitleSep = ": "

// shortParentMs is the length below which a parent (part/section) heading is
// folded into its first child instead of kept as its own chapter. A heading
// that short is just the narrator reading the title. Mirrors Libation.
const shortParentMs = 10_000

// flattenChapters turns Audible's chapter tree into a flat list, prefixing
// each child's title with its parents' titles. A parent shorter than
// shortParentMs is merged into its first child (which then starts where the
// parent started); a longer parent is kept as a chapter of its own.
// The input is not modified.
func flattenChapters(chapters []audible.AudibleChapter) []audible.AudibleChapter {
	var out []audible.AudibleChapter
	for _, c := range chapters {
		if len(c.Chapters) == 0 {
			out = append(out, audible.AudibleChapter{Title: c.Title, StartOffsetMs: c.StartOffsetMs, LengthMs: c.LengthMs})
			continue
		}

		children := flattenChapters(c.Chapters)
		if c.LengthMs < shortParentMs {
			children[0].StartOffsetMs = c.StartOffsetMs
			children[0].LengthMs += c.LengthMs
		} else {
			out = append(out, audible.AudibleChapter{Title: c.Title, StartOffsetMs: c.StartOffsetMs, LengthMs: c.LengthMs})
		}
		for i := range children {
			children[i].Title = c.Title + nestedTitleSep + children[i].Title
		}
		out = append(out, children...)
	}
	return out
}

// buildOutline flattens Audible's chapter info into contiguous chapters: each
// chapter ends where the next one starts, so there are no gaps, and the last
// ends at the book's runtime. Chapters left with no duration are dropped.
func buildOutline(info *audible.ChapterInfo) []OutlineChapter {
	if info == nil {
		return nil
	}
	flat := flattenChapters(info.Chapters)
	sort.SliceStable(flat, func(i, j int) bool { return flat[i].StartOffsetMs < flat[j].StartOffsetMs })

	out := make([]OutlineChapter, 0, len(flat))
	for i, c := range flat {
		end := c.StartOffsetMs + c.LengthMs
		if i+1 < len(flat) {
			end = flat[i+1].StartOffsetMs
		} else if info.RuntimeLengthMs > end {
			end = info.RuntimeLengthMs
		}
		if end <= c.StartOffsetMs {
			continue
		}
		out = append(out, OutlineChapter{Title: strings.TrimSpace(c.Title), StartMs: c.StartOffsetMs, EndMs: end})
	}
	return out
}

// ffmetadata renders chapters in ffmpeg's FFMETADATA1 format, for use as an
// extra ffmpeg input with -map_chapters.
func ffmetadata(chapters []OutlineChapter) string {
	var b strings.Builder
	b.WriteString(";FFMETADATA1\n")
	for _, c := range chapters {
		fmt.Fprintf(&b, "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=%d\nEND=%d\ntitle=%s\n",
			c.StartMs, c.EndMs, escapeFFMetadata(c.Title))
	}
	return b.String()
}

var ffmetadataEscaper = strings.NewReplacer(
	`\`, `\\`, `=`, `\=`, `;`, `\;`, `#`, `\#`, "\n", "\\\n",
)

func escapeFFMetadata(s string) string { return ffmetadataEscaper.Replace(s) }

// cueSheet renders a cue sheet pointing at audioFileName. Cue sheets index in
// frames of 1/75 s. The file type is always MP3, as Libation writes it: the
// cue format has no MP4 type and players that read cue files accept it.
func cueSheet(audioFileName string, chapters []OutlineChapter) string {
	var b strings.Builder
	fmt.Fprintf(&b, "FILE %q MP3\n", strings.ReplaceAll(audioFileName, `"`, "'"))
	for i, c := range chapters {
		min := c.StartMs / 60_000
		sec := c.StartMs / 1000 % 60
		frames := c.StartMs % 1000 * 75 / 1000
		fmt.Fprintf(&b, "TRACK %d AUDIO\n", i+1)
		fmt.Fprintf(&b, "  TITLE \"%s\"\n", strings.ReplaceAll(c.Title, `"`, "'"))
		fmt.Fprintf(&b, "  INDEX 01 %02d:%02d:%02d\n", min, sec, frames)
	}
	return b.String()
}

// outlineDoc is the content of <book>.chapters.json: the flat chapters as
// embedded in the audio, plus Audible's original nested outline.
type outlineDoc struct {
	ASIN      string               `json:"asin"`
	Title     string               `json:"title"`
	AudioFile string               `json:"audio_file"`
	RuntimeMs int64                `json:"runtime_ms"`
	Chapters  []OutlineChapter     `json:"chapters"`
	Audible   *audible.ChapterInfo `json:"audible_chapter_info"`
}

// writeOutlineFiles writes <audio file name>.cue and .chapters.json next to
// audioFile.
func writeOutlineFiles(audioFile string, job DownloadJob, info *audible.ChapterInfo, chapters []OutlineChapter) error {
	base := strings.TrimSuffix(audioFile, filepath.Ext(audioFile))
	name := filepath.Base(audioFile)

	if err := os.WriteFile(base+".cue", []byte(cueSheet(name, chapters)), 0644); err != nil {
		return fmt.Errorf("write cue: %w", err)
	}

	doc, err := json.MarshalIndent(outlineDoc{
		ASIN:      job.AudibleID,
		Title:     job.Title,
		AudioFile: name,
		RuntimeMs: info.RuntimeLengthMs,
		Chapters:  chapters,
		Audible:   info,
	}, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(base+".chapters.json", doc, 0644); err != nil {
		return fmt.Errorf("write chapters json: %w", err)
	}
	return nil
}
