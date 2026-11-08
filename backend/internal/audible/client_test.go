package audible

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestDownloadPDF_NotAvailable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`{"detail":"No PDF available for this title"}`))
	}))
	defer srv.Close()

	client := NewClient(srv.URL)
	tmpDir := t.TempDir()
	destPath := filepath.Join(tmpDir, "book.pdf")

	got, err := client.DownloadPDF(context.Background(), "acc1", "B0001", destPath)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got {
		t.Error("expected false (no PDF), got true")
	}
	if _, err := os.Stat(destPath); !os.IsNotExist(err) {
		t.Error("expected no file to be created")
	}
}

func TestDownloadPDF_Success(t *testing.T) {
	pdfContent := []byte("%PDF-1.4 fake pdf content")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/download/acc1/B0001/pdf" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/pdf")
		w.Write(pdfContent)
	}))
	defer srv.Close()

	client := NewClient(srv.URL)
	tmpDir := t.TempDir()
	destPath := filepath.Join(tmpDir, "book.pdf")

	got, err := client.DownloadPDF(context.Background(), "acc1", "B0001", destPath)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !got {
		t.Error("expected true (PDF downloaded), got false")
	}
	data, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("read output file: %v", err)
	}
	if string(data) != string(pdfContent) {
		t.Errorf("file content mismatch: got %q, want %q", data, pdfContent)
	}
}

func TestDownloadPDF_ServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		w.Write([]byte(`{"detail":"upstream error"}`))
	}))
	defer srv.Close()

	client := NewClient(srv.URL)
	tmpDir := t.TempDir()
	destPath := filepath.Join(tmpDir, "book.pdf")

	_, err := client.DownloadPDF(context.Background(), "acc1", "B0001", destPath)
	if err == nil {
		t.Error("expected error for 502 response, got nil")
	}
}

func TestGetChapters(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/download/acc1/B0001/chapters" {
			http.NotFound(w, r)
			return
		}
		w.Write([]byte(`{"brandIntroDurationMs":1532,"runtime_length_ms":20000,"is_accurate":true,
			"chapters":[{"title":"Part 1","start_offset_ms":0,"length_ms":3000,
			"chapters":[{"title":"Chapter 1","start_offset_ms":3000,"length_ms":17000}]}]}`))
	}))
	defer srv.Close()

	info, err := NewClient(srv.URL).GetChapters(context.Background(), "acc1", "B0001")
	if err != nil {
		t.Fatal(err)
	}
	if info.RuntimeLengthMs != 20000 || info.BrandIntroDurationMs != 1532 || !info.IsAccurate {
		t.Errorf("unexpected info: %+v", info)
	}
	if len(info.Chapters) != 1 || info.Chapters[0].Chapters[0].Title != "Chapter 1" {
		t.Errorf("nested chapters not decoded: %+v", info.Chapters)
	}
}
