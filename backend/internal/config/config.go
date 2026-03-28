package config

import (
	"log"

	"github.com/spf13/viper"
)

type Config struct {
	Port            string
	DatabasePath    string
	AudibleSvcURL   string
	AppURL          string
	OutputDir       string
	DownloadWorkers int
}

func Load() *Config {
	viper.SetDefault("PORT", "8080")
	viper.SetDefault("DATABASE_PATH", "./data/libation.db")
	viper.SetDefault("AUDIBLE_SVC_URL", "http://localhost:8081")
	viper.SetDefault("APP_URL", "http://localhost:8080")
	viper.SetDefault("OUTPUT_DIR", "./data/audiobooks")
	viper.SetDefault("DOWNLOAD_WORKERS", 3)

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
	}
}
