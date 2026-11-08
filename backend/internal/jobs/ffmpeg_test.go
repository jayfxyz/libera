package jobs

import (
	"context"
	"testing"

	"github.com/web-libation/backend/internal/audible"
)

func TestBuildDecryptCmd_M4B_AAXC(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aaxc", Key: "abc123", IV: "def456"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aaxc", "/out/book.m4b", "m4b", "")

	args := cmd.Args
	assertContains(t, args, "-audible_key", "abc123")
	assertContains(t, args, "-audible_iv", "def456")
	assertContains(t, args, "-c:a", "copy")
	assertNotContains(t, args, "libmp3lame")
	if args[len(args)-1] != "/out/book.m4b" {
		t.Errorf("last arg should be output file, got %q", args[len(args)-1])
	}
}

func TestBuildDecryptCmd_MP3_AAXC(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aaxc", Key: "abc123", IV: "def456"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aaxc", "/out/book.mp3", "mp3", "")

	args := cmd.Args
	assertContains(t, args, "-audible_key", "abc123")
	assertContains(t, args, "-c:a", "libmp3lame")
	assertContains(t, args, "-q:a", "2")
	assertNotContains(t, args, "copy")
	if args[len(args)-1] != "/out/book.mp3" {
		t.Errorf("last arg should be output file, got %q", args[len(args)-1])
	}
}

func TestBuildDecryptCmd_M4B_AAX(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aax", ActivationBytes: "deadbeef"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aax", "/out/book.m4b", "m4b", "")

	args := cmd.Args
	assertContains(t, args, "-activation_bytes", "deadbeef")
	assertContains(t, args, "-c:a", "copy")
	assertNotContains(t, args, "libmp3lame")
}

func TestBuildDecryptCmd_MP3_AAX(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aax", ActivationBytes: "deadbeef"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aax", "/out/book.mp3", "mp3", "")

	args := cmd.Args
	assertContains(t, args, "-activation_bytes", "deadbeef")
	assertContains(t, args, "-c:a", "libmp3lame")
	assertContains(t, args, "-q:a", "2")
}

// assertContains checks that needle appears immediately after key in args.
func assertContains(t *testing.T, args []string, key, needle string) {
	t.Helper()
	for i, a := range args {
		if a == key && i+1 < len(args) && args[i+1] == needle {
			return
		}
	}
	t.Errorf("args %v: expected %q %q pair, not found", args, key, needle)
}

func assertNotContains(t *testing.T, args []string, val string) {
	t.Helper()
	for _, a := range args {
		if a == val {
			t.Errorf("args %v: expected %q to be absent, but found it", args, val)
			return
		}
	}
}

func TestBuildDecryptCmd_WithChapters(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aaxc", Key: "k", IV: "i"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aaxc", "/out/book.m4b", "m4b", "/tmp/ch.ffmetadata")

	args := cmd.Args
	assertContains(t, args, "-i", "/tmp/ch.ffmetadata")
	assertContains(t, args, "-map", "0:a")
	assertContains(t, args, "-map_metadata", "0")
	assertContains(t, args, "-map_chapters", "1")
	// decryption key options must come before the encrypted input, not the metadata one
	for i, a := range args {
		if a == "-audible_key" && i > indexOf(args, "/tmp/in.aaxc") {
			t.Error("-audible_key must precede the encrypted input")
		}
	}
	if indexOf(args, "/tmp/in.aaxc") > indexOf(args, "/tmp/ch.ffmetadata") {
		t.Error("encrypted audio must be input 0")
	}
}

func TestBuildDecryptCmd_WithoutChapters(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aax", ActivationBytes: "deadbeef"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aax", "/out/book.m4b", "m4b", "")
	assertNotContains(t, cmd.Args, "-map_chapters")
}

func indexOf(args []string, s string) int {
	for i, a := range args {
		if a == s {
			return i
		}
	}
	return -1
}
