package jobs

import (
	"regexp"
	"strings"
)

// FilenameData holds the book metadata available for filename template substitution.
type FilenameData struct {
	Title       string
	Authors     string // comma-separated
	Narrators   string // comma-separated
	SeriesName  string
	SeriesIndex string
	Year        string
	Language    string
	DurationH   string // integer hours, e.g. "21"
}

// sentinelCleanRe removes an empty-tag sentinel together with any
// immediately surrounding separator characters (-, _, ,, /).
var sentinelCleanRe = regexp.MustCompile(`\s*[-_,/]\s*\x00|\x00\s*[-_,/]\s*|\x00`)

// renderFilename substitutes template tags with book metadata.
// Supported tags: {title} {author} {narrator} {series} {series_index} {year} {language} {duration_h}.
// Empty values are removed together with any surrounding separator to avoid artifacts like "Title - ".
// Falls back to {title} when tmpl is empty.
func renderFilename(tmpl string, data FilenameData) string {
	if tmpl == "" {
		tmpl = "{title}"
	}

	subs := [][2]string{
		{"{title}", data.Title},
		{"{author}", data.Authors},
		{"{narrator}", data.Narrators},
		{"{series}", data.SeriesName},
		{"{series_index}", data.SeriesIndex},
		{"{year}", data.Year},
		{"{language}", data.Language},
		{"{duration_h}", data.DurationH},
	}

	result := tmpl
	for _, kv := range subs {
		tag, val := kv[0], kv[1]
		if val == "" {
			result = strings.ReplaceAll(result, tag, "\x00")
		} else {
			safe := unsafeChars.ReplaceAllString(val, "_")
			result = strings.ReplaceAll(result, tag, safe)
		}
	}

	// Remove empty sentinels and their surrounding separators.
	result = sentinelCleanRe.ReplaceAllString(result, "")
	result = strings.TrimSpace(result)

	if result == "" {
		result = unsafeChars.ReplaceAllString(data.Title, "_")
	}

	return sanitizeFilename(result)
}
