package jobs

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os/exec"
	"strconv"
	"strings"
)

// Chapter represents one chapter from ffprobe output.
type Chapter struct {
	ID       int
	Title    string
	StartSec float64
	EndSec   float64
}

// parseChapters parses the JSON output of ffprobe -show_chapters -of json.
func parseChapters(data []byte) ([]Chapter, error) {
	var raw struct {
		Chapters []struct {
			ID        int               `json:"id"`
			StartTime string            `json:"start_time"`
			EndTime   string            `json:"end_time"`
			Tags      map[string]string `json:"tags"`
		} `json:"chapters"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, err
	}

	chapters := make([]Chapter, 0, len(raw.Chapters))
	for _, rc := range raw.Chapters {
		start, _ := strconv.ParseFloat(rc.StartTime, 64)
		end, _ := strconv.ParseFloat(rc.EndTime, 64)
		chapters = append(chapters, Chapter{
			ID:       rc.ID,
			Title:    rc.Tags["title"],
			StartSec: start,
			EndSec:   end,
		})
	}
	return chapters, nil
}

// buildChapterCmd builds an ffmpeg command that extracts a single chapter
// from decryptedFile into outFile by start/end time (stream copy, no re-encode).
func buildChapterCmd(ctx context.Context, decryptedFile, outFile string, startSec, endSec float64) *exec.Cmd {
	return exec.CommandContext(ctx, "ffmpeg", "-y",
		"-ss", fmt.Sprintf("%f", startSec),
		"-to", fmt.Sprintf("%f", endSec),
		"-i", decryptedFile,
		"-c", "copy",
		outFile,
	)
}

// splitIntoChapters probes decryptedFile for chapter metadata and extracts each
// chapter to a separate file in outputDir. Returns an error only if ffprobe fails;
// individual chapter failures are logged and skipped.
func splitIntoChapters(ctx context.Context, decryptedFile, outputDir, bookTitle, tmpl string, job DownloadJob) error {
	probe, err := exec.CommandContext(ctx, "ffprobe",
		"-v", "quiet", "-show_chapters", "-of", "json", decryptedFile,
	).Output()
	if err != nil {
		return fmt.Errorf("ffprobe: %w", err)
	}

	chapters, err := parseChapters(probe)
	if err != nil {
		return fmt.Errorf("parse chapters: %w", err)
	}
	if len(chapters) == 0 {
		return nil
	}

	bookBase := renderFilename(tmpl, FilenameData{
		Title: bookTitle, Authors: job.Authors, SeriesName: job.SeriesName,
		SeriesIndex: job.SeriesIndex, Year: job.Year, Language: job.Language, DurationH: job.DurationH,
	})

	ext := "." + job.Format
	for i, ch := range chapters {
		outPath := chapterFilename(outputDir, bookBase, i, ch.Title) + ext
		cmd := buildChapterCmd(ctx, decryptedFile, outPath, ch.StartSec, ch.EndSec)
		if out, cerr := cmd.CombinedOutput(); cerr != nil {
			log.Printf("chapter %d extract failed: %s", i, strings.TrimSpace(string(out)))
		}
	}
	return nil
}

// chapterFilename generates a safe output filename for one chapter.
func chapterFilename(baseDir, bookBase string, n int, title string) string {
	chTitle := sanitizeFilename(title)
	if chTitle == "" || chTitle == "audiobook" {
		chTitle = fmt.Sprintf("Chapter_%02d", n+1)
	}
	name := fmt.Sprintf("%s - %02d - %s", bookBase, n+1, chTitle)
	return baseDir + "/" + sanitizeFilename(name)
}
