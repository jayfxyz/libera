package db_test

import (
	"testing"

	"github.com/web-libation/backend/internal/db"
)

func TestSettings_GetSetRoundtrip(t *testing.T) {
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatalf("open memory db: %v", err)
	}
	defer database.Close()
	if err := db.Migrate(database); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	// A key that doesn't exist yet should return "", false
	val, ok, err := db.GetSetting(database, "output_dir")
	if err != nil {
		t.Fatalf("GetSetting: %v", err)
	}
	if ok {
		t.Errorf("expected ok=false for missing key, got value=%q", val)
	}

	// Set a value
	if err := db.SetSetting(database, "output_dir", "/audiobooks"); err != nil {
		t.Fatalf("SetSetting: %v", err)
	}

	// Read it back
	val, ok, err = db.GetSetting(database, "output_dir")
	if err != nil {
		t.Fatalf("GetSetting after set: %v", err)
	}
	if !ok {
		t.Fatal("expected ok=true after SetSetting")
	}
	if val != "/audiobooks" {
		t.Errorf("got %q, want %q", val, "/audiobooks")
	}

	// Overwrite — should update, not duplicate
	if err := db.SetSetting(database, "output_dir", "/new/path"); err != nil {
		t.Fatalf("SetSetting overwrite: %v", err)
	}
	val, _, _ = db.GetSetting(database, "output_dir")
	if val != "/new/path" {
		t.Errorf("after overwrite got %q, want %q", val, "/new/path")
	}
}

func TestSettings_LoadAll(t *testing.T) {
	database, err := db.OpenMemory()
	if err != nil {
		t.Fatalf("open memory db: %v", err)
	}
	defer database.Close()
	if err := db.Migrate(database); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	db.SetSetting(database, "output_dir", "/audio")
	db.SetSetting(database, "download_workers", "5")
	db.SetSetting(database, "default_format", "mp3")

	all, err := db.LoadAllSettings(database)
	if err != nil {
		t.Fatalf("LoadAllSettings: %v", err)
	}

	cases := map[string]string{
		"output_dir":       "/audio",
		"download_workers": "5",
		"default_format":   "mp3",
	}
	for k, want := range cases {
		if got := all[k]; got != want {
			t.Errorf("LoadAll[%q] = %q, want %q", k, got, want)
		}
	}
	if len(all) != 3 {
		t.Errorf("expected 3 settings, got %d", len(all))
	}
}
