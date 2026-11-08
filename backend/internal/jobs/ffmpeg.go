package jobs

import (
	"context"
	"os/exec"

	"github.com/web-libation/backend/internal/audible"
)

// buildDecryptCmd builds the ffmpeg command that decrypts an AAX/AAXC file and
// writes the output. When format is "mp3" the audio is re-encoded with LAME;
// otherwise the stream is copied without re-encoding (format "m4b" or any other).
//
// When chaptersFile (an FFMETADATA1 file) is set, its chapters replace the ones
// embedded in the Audible file; the source's other metadata tags are kept.
func buildDecryptCmd(ctx context.Context, info *audible.DownloadInfoResponse, srcFile, outFile, format, chaptersFile string) *exec.Cmd {
	args := []string{"-y"}

	if info.Format == "aaxc" {
		args = append(args, "-audible_key", info.Key, "-audible_iv", info.IV)
	} else {
		args = append(args, "-activation_bytes", info.ActivationBytes)
	}

	args = append(args, "-i", srcFile)
	if chaptersFile != "" {
		args = append(args, "-i", chaptersFile,
			"-map", "0:a", "-map_metadata", "0", "-map_chapters", "1")
	}
	args = append(args, "-vn")

	if format == "mp3" {
		// VBR quality 2 ≈ 170–210 kbps — excellent quality, widely compatible.
		args = append(args, "-c:a", "libmp3lame", "-q:a", "2")
	} else {
		args = append(args, "-c:a", "copy")
	}

	args = append(args, outFile)
	return exec.CommandContext(ctx, "ffmpeg", args...)
}
