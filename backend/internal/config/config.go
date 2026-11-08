package config

import (
	"log"
	"strconv"
	"sync"

	"github.com/spf13/viper"
)

type Config struct {
	mu sync.RWMutex

	Port             string
	DatabasePath     string
	AudibleSvcURL    string
	AppURL           string
	OutputDir        string
	DownloadWorkers  int
	DefaultFormat    string // "m4b" or "mp3"
	FilenameTemplate string // e.g. "{author} - {title}"
	// FolderTemplate names the per-book folder created inside OutputDir to hold
	// the audio and its companion files. Empty puts files directly in OutputDir.
	FolderTemplate string
}

// DefaultFolderTemplate gives "Patrick Rothfuss - The Name of the Wind".
const DefaultFolderTemplate = "{author} - {title}"

func Load() *Config {
	viper.SetDefault("PORT", "8080")
	viper.SetDefault("DATABASE_PATH", "./data/libation.db")
	viper.SetDefault("AUDIBLE_SVC_URL", "http://localhost:8081")
	viper.SetDefault("APP_URL", "http://localhost:8080")
	viper.SetDefault("OUTPUT_DIR", "./data/audiobooks")
	viper.SetDefault("DOWNLOAD_WORKERS", 3)
	viper.SetDefault("DEFAULT_FORMAT", "m4b")
	viper.SetDefault("FILENAME_TEMPLATE", "{title}")
	viper.SetDefault("FOLDER_TEMPLATE", DefaultFolderTemplate)

	viper.SetConfigFile(".env")
	viper.SetConfigType("env")
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err != nil {
		log.Println("no .env file found, using environment variables and defaults")
	}

	return &Config{
		Port:             viper.GetString("PORT"),
		DatabasePath:     viper.GetString("DATABASE_PATH"),
		AudibleSvcURL:    viper.GetString("AUDIBLE_SVC_URL"),
		AppURL:           viper.GetString("APP_URL"),
		OutputDir:        viper.GetString("OUTPUT_DIR"),
		DownloadWorkers:  viper.GetInt("DOWNLOAD_WORKERS"),
		DefaultFormat:    viper.GetString("DEFAULT_FORMAT"),
		FilenameTemplate: viper.GetString("FILENAME_TEMPLATE"),
		FolderTemplate:   viper.GetString("FOLDER_TEMPLATE"),
	}
}

// ApplyDBOverrides overlays settings persisted in the database on top of the
// environment-variable defaults. Called once at startup after DB migration.
func (c *Config) ApplyDBOverrides(overrides map[string]string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if v, ok := overrides["output_dir"]; ok {
		c.OutputDir = v
	}
	if v, ok := overrides["download_workers"]; ok {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			c.DownloadWorkers = n
		}
	}
	if v, ok := overrides["default_format"]; ok && (v == "m4b" || v == "mp3") {
		c.DefaultFormat = v
	}
	if v, ok := overrides["filename_template"]; ok {
		c.FilenameTemplate = v
	}
	if v, ok := overrides["folder_template"]; ok {
		c.FolderTemplate = v
	}
}

// Update applies a settings patch in-memory. Values are already persisted to
// the DB by the caller before this is invoked.
func (c *Config) Update(key, value string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	switch key {
	case "output_dir":
		c.OutputDir = value
	case "download_workers":
		if n, err := strconv.Atoi(value); err == nil && n > 0 {
			c.DownloadWorkers = n
		}
	case "default_format":
		if value == "m4b" || value == "mp3" {
			c.DefaultFormat = value
		}
	case "filename_template":
		c.FilenameTemplate = value
	case "folder_template":
		c.FolderTemplate = value
	}
}

// Settings is a consistent snapshot of the user-editable settings.
type Settings struct {
	OutputDir        string
	DefaultFormat    string
	FilenameTemplate string
	FolderTemplate   string
	DownloadWorkers  int
}

func (c *Config) Read() Settings {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return Settings{
		OutputDir:        c.OutputDir,
		DefaultFormat:    c.DefaultFormat,
		FilenameTemplate: c.FilenameTemplate,
		FolderTemplate:   c.FolderTemplate,
		DownloadWorkers:  c.DownloadWorkers,
	}
}

// OutputDirectory returns the current output directory.
func (c *Config) OutputDirectory() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.OutputDir
}
