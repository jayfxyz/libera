package jobs

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"

	"path/filepath"
	"regexp"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

func (q *Queue) process(job DownloadJob) {
	// Reconstruct the trace context from the enqueuing HTTP request so that
	// the worker span is a child of the original request trace.
	carrier := propagation.MapCarrier(job.TraceCarrier)
	parentCtx := otel.GetTextMapPropagator().Extract(q.cancelCtx, carrier)

	tracer := otel.Tracer("jobs")
	ctx, span := tracer.Start(parentCtx, "job.process",
		trace.WithAttributes(
			attribute.String("job.id", job.ID),
			attribute.String("job.asin", job.AudibleID),
			attribute.String("job.title", job.Title),
			attribute.String("job.format", job.Format),
		),
	)
	defer span.End()

	// Register a per-job cancel so DELETE /downloads/{id} can stop this job.
	ctx, jobCancel := context.WithCancel(ctx)
	defer jobCancel()
	q.registerCancel(job.ID, jobCancel)
	defer q.deregisterCancel(job.ID)

	log.Printf("starting download job %s asin=%s", job.ID, job.AudibleID)
	q.setStatus(job.ID, "downloading", 0, "")

	// Get download URL + decryption info from sidecar
	info, err := q.audible.GetDownloadInfo(ctx, job.AudibleAccountID, job.AudibleID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("get download info: %v", err))
		q.markError(job.BookID)
		return
	}

	isAAXC := info.Format == "aaxc"
	if !isAAXC && info.ActivationBytes == "" {
		err := fmt.Errorf("no activation bytes — account not fully authorized")
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		q.setStatus(job.ID, "error", 0, err.Error())
		q.markError(job.BookID)
		return
	}
	if isAAXC && (info.Key == "" || info.IV == "") {
		err := fmt.Errorf("missing AAXC decryption key/iv")
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		q.setStatus(job.ID, "error", 0, err.Error())
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

	_, downloadSpan := tracer.Start(ctx, "job.download",
		trace.WithAttributes(attribute.Bool("download.aaxc", isAAXC)),
	)
	if err := streamDownload(ctx, info.DownloadURL, tmpFile, func(pct float64) {
		q.setStatus(job.ID, "downloading", pct, "")
	}); err != nil {
		downloadSpan.RecordError(err)
		downloadSpan.SetStatus(codes.Error, err.Error())
		downloadSpan.End()
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("download: %v", err))
		q.markError(job.BookID)
		return
	}
	downloadSpan.End()

	// Sanity-check the downloaded file
	fi, err := os.Stat(tmpFile)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("stat downloaded file: %v", err))
		q.markError(job.BookID)
		return
	}
	log.Printf("job %s: downloaded %d bytes", job.ID, fi.Size())
	const minAudiobookBytes = 1024 * 1024
	if fi.Size() < minAudiobookBytes {
		// Too small to be a real audiobook — peek at content for diagnostics
		snippet := make([]byte, 512)
		if f, ferr := os.Open(tmpFile); ferr == nil {
			n, _ := f.Read(snippet)
			f.Close()
			snippet = snippet[:n]
		}
		errMsg := fmt.Sprintf("download returned %d bytes (expected an audiobook file): %s", fi.Size(), strings.TrimSpace(string(snippet)))
		err := errors.New(errMsg)
		span.RecordError(err)
		span.SetStatus(codes.Error, errMsg)
		q.setStatus(job.ID, "error", 0, errMsg)
		q.markError(job.BookID)
		return
	}

	// Decrypt with ffmpeg
	q.setStatus(job.ID, "decrypting", 100, "")

	if err := os.MkdirAll(job.OutputDir, 0755); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("mkdir: %v", err))
		return
	}

	outName := sanitizeFilename(job.Title) + "." + job.Format
	outFile := filepath.Join(job.OutputDir, outName)

	_, ffmpegSpan := tracer.Start(ctx, "job.ffmpeg",
		trace.WithAttributes(
			attribute.String("ffmpeg.format", job.Format),
			attribute.Bool("ffmpeg.aaxc", isAAXC),
		),
	)
	cmd := buildDecryptCmd(ctx, info, tmpFile, outFile, job.Format)
	if out, err := cmd.CombinedOutput(); err != nil {
		ffmpegSpan.RecordError(err)
		ffmpegSpan.SetStatus(codes.Error, strings.TrimSpace(string(out)))
		ffmpegSpan.End()
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		q.setStatus(job.ID, "error", 0, fmt.Sprintf("ffmpeg: %s", strings.TrimSpace(string(out))))
		q.markError(job.BookID)
		return
	}
	ffmpegSpan.End()

	q.markLiberated(job.BookID, job.Format)

	// Best-effort PDF companion download — does not affect job status on failure.
	pdfPath := filepath.Join(job.OutputDir, sanitizeFilename(job.Title)+".pdf")
	if downloaded, pdfErr := q.audible.DownloadPDF(ctx, job.AudibleAccountID, job.AudibleID, pdfPath); pdfErr != nil {
		log.Printf("job %s: PDF download failed (non-fatal): %v", job.ID, pdfErr)
	} else if downloaded {
		log.Printf("job %s: PDF saved: %s", job.ID, pdfPath)
	}

	log.Printf("job %s done: %s", job.ID, outFile)
	q.setStatus(job.ID, "done", 100, outFile)
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
