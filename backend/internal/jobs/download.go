package jobs

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

func (q *Queue) process(job DownloadJob) {
	log.Printf("starting download job %s asin=%s", job.ID, job.AudibleID)
	q.setStatus(job.ID, "downloading", 0, "")

	ctx := q.cancelCtx

	// Get download URL + decryption info from sidecar
	info, err := q.audible.GetDownloadInfo(ctx, job.AudibleAccountID, job.AudibleID)
	if err != nil {
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("get download info: %v", err))
		q.markError(job.BookID)
		return
	}

	isAAXC := info.Format == "aaxc"
	if !isAAXC && info.ActivationBytes == "" {
		q.setStatus(job.ID, "error", 0, "no activation bytes — account not fully authorized")
		q.markError(job.BookID)
		return
	}
	if isAAXC && (info.Key == "" || info.IV == "") {
		q.setStatus(job.ID, "error", 0, "missing AAXC decryption key/iv")
		q.markError(job.BookID)
		return
	}

	srcExt := ".aax"
	if isAAXC {
		srcExt = ".aaxc"
	}

	// Stream download to temp file
	tmpFile := filepath.Join(os.TempDir(), job.ID+srcExt)
	defer os.Remove(tmpFile)

	if err := streamDownload(ctx, info.DownloadURL, tmpFile, func(pct float64) {
		q.setStatus(job.ID, "downloading", pct, "")
	}); err != nil {
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("download: %v", err))
		q.markError(job.BookID)
		return
	}

	// Sanity-check the downloaded file
	if fi, err := os.Stat(tmpFile); err == nil {
		log.Printf("job %s: downloaded %d bytes", job.ID, fi.Size())
		if f, err := os.Open(tmpFile); err == nil {
			magic := make([]byte, 12)
			n, _ := f.Read(magic)
			f.Close()
			log.Printf("job %s: first %d bytes: %x", job.ID, n, magic[:n])
		}
	}

	// Decrypt with ffmpeg
	q.setStatus(job.ID, "decrypting", 100, "")

	if err := os.MkdirAll(job.OutputDir, 0755); err != nil {
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("mkdir: %v", err))
		return
	}

	outName := sanitizeFilename(job.Title) + "." + job.Format
	outFile := filepath.Join(job.OutputDir, outName)

	var cmd *exec.Cmd
	if isAAXC {
		cmd = exec.CommandContext(ctx, "ffmpeg",
			"-y",
			"-audible_key", info.Key,
			"-audible_iv", info.IV,
			"-i", tmpFile,
			"-vn", "-c:a", "copy",
			outFile,
		)
	} else {
		cmd = exec.CommandContext(ctx, "ffmpeg",
			"-y",
			"-activation_bytes", info.ActivationBytes,
			"-i", tmpFile,
			"-vn", "-c:a", "copy",
			outFile,
		)
	}
	if out, err := cmd.CombinedOutput(); err != nil {
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("ffmpeg: %s", strings.TrimSpace(string(out))))
		q.markError(job.BookID)
		return
	}

	log.Printf("job %s done: %s", job.ID, outFile)
	q.setStatus(job.ID, "done", 100, outFile)
	q.markLiberated(job.BookID, job.Format)
}

func streamDownload(ctx context.Context, url, dest string, onProgress func(float64)) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "Audible/3.56.2 iOS/15.0.0 iPhone")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()

	total := resp.ContentLength
	var downloaded int64
	buf := make([]byte, 32*1024)

	lastReport := time.Now()
	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			if _, werr := f.Write(buf[:n]); werr != nil {
				return werr
			}
			downloaded += int64(n)
			if total > 0 && time.Since(lastReport) > 500*time.Millisecond {
				onProgress(float64(downloaded) / float64(total) * 100)
				lastReport = time.Now()
			}
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
	}
	return nil
}

var unsafeChars = regexp.MustCompile(`[<>:"/\\|?*\x00-\x1f]`)

func sanitizeFilename(s string) string {
	s = unsafeChars.ReplaceAllString(s, "_")
	s = strings.TrimSpace(s)
	if len(s) > 200 {
		s = s[:200]
	}
	if s == "" {
		s = "audiobook"
	}
	return s
}
