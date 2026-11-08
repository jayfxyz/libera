package api

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestAudioFilesOnDisk_FindsFilesInBookFolders(t *testing.T) {
	root := t.TempDir()
	write := func(rel string) {
		p := filepath.Join(root, rel)
		if err := os.MkdirAll(filepath.Dir(p), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, nil, 0644); err != nil {
			t.Fatal(err)
		}
	}
	write("Loose Book.mp3")
	write("Patrick Rothfuss - The Name of the Wind/The Name of the Wind.m4b")
	write("Patrick Rothfuss - The Name of the Wind/The Name of the Wind.cue")
	write("Patrick Rothfuss - The Name of the Wind/The Name of the Wind.chapters.json")
	write(".Trash/Deleted.m4b")

	got, err := audioFilesOnDisk(root)
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]string{"Loose Book": "mp3", "The Name of the Wind": "m4b"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %v, want %v", got, want)
	}
}
