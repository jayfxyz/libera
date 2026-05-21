package config

import (
	"log"
	"strconv"
	"sync"

	"github.com/spf13/viper"
)

type Config struct {
	mu sync.RWMutex

	Port            string
	DatabasePath    string
	AudibleSvcURL   string
	AppURL          string
	OutputDir       string
	DownloadWorkers int
	DefaultFormat   string // "m4b" or "mp3"
}

func Load() *Config {
	viper.SetDefault("PORT", "8080")
	viper.SetDefault("DATABASE_PATH", "./data/libation.db")
	viper.SetDefault("AUDIBLE_SVC_URL", "http://localhost:8081")
	viper.SetDefault("APP_URL", "http://localhost:8080")
	viper.SetDefault("OUTPUT_DIR", "./data/audiobooks")
	viper.SetDefault("DOWNLOAD_WORKERS", 3)
	viper.SetDefault("DEFAULT_FORMAT", "m4b")

	viper.SetConfigFile(".env")
	viper.SetConfigType("env")
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err != nil {
		log.Println("no .env file found, using environment variables and defaults")
	}

	return &Config{
		Port:            viper.GetString("PORT"),
		DatabasePath:    viper.GetString("DATABASE_PATH"),
		AudibleSvcURL:   viper.GetString("AUDIBLE_SVC_URL"),
		AppURL:          viper.GetString("APP_URL"),
		OutputDir:       viper.GetString("OUTPUT_DIR"),
		DownloadWorkers: viper.GetInt("DOWNLOAD_WORKERS"),
		DefaultFormat:   viper.GetString("DEFAULT_FORMAT"),
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
	}
}

func (c *Config) Read() (outputDir, defaultFormat string, downloadWorkers int) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.OutputDir, c.DefaultFormat, c.DownloadWorkers
}
