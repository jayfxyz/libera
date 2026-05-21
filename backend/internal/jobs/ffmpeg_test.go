package jobs

import (
	"context"
	"testing"

	"github.com/web-libation/backend/internal/audible"
)

func TestBuildDecryptCmd_M4B_AAXC(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aaxc", Key: "abc123", IV: "def456"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aaxc", "/out/book.m4b", "m4b")

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
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aaxc", "/out/book.mp3", "mp3")

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
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aax", "/out/book.m4b", "m4b")

	args := cmd.Args
	assertContains(t, args, "-activation_bytes", "deadbeef")
	assertContains(t, args, "-c:a", "copy")
	assertNotContains(t, args, "libmp3lame")
}

func TestBuildDecryptCmd_MP3_AAX(t *testing.T) {
	info := &audible.DownloadInfoResponse{Format: "aax", ActivationBytes: "deadbeef"}
	cmd := buildDecryptCmd(context.Background(), info, "/tmp/in.aax", "/out/book.mp3", "mp3")

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
