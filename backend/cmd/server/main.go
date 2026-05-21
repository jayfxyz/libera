package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/web-libation/backend/internal/api"
	"github.com/web-libation/backend/internal/audible"
	"github.com/web-libation/backend/internal/config"
	"github.com/web-libation/backend/internal/db"
	"github.com/web-libation/backend/internal/jobs"
	"github.com/web-libation/backend/internal/telemetry"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

func main() {
	cfg := config.Load()

	shutdownTracing := telemetry.Init(context.Background())
	defer func() {
		tctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		shutdownTracing(tctx)
	}()

	database, err := db.Open(cfg.DatabasePath)
	if err != nil {
		log.Fatalf("failed to open database: %v", err)
	}
	defer database.Close()

	if err := db.Migrate(database); err != nil {
		log.Fatalf("failed to run migrations: %v", err)
	}

	// Overlay any user-persisted settings on top of env-var defaults.
	if overrides, err := db.LoadAllSettings(database); err == nil {
		cfg.ApplyDBOverrides(overrides)
	} else {
		log.Printf("warning: could not load settings from DB: %v", err)
	}

	audibleClient := audible.NewClient(cfg.AudibleSvcURL, audible.WithTracedTransport())
	downloadQueue := jobs.NewQueue(cfg.DownloadWorkers, audibleClient, database)
	downloadQueue.Start()
	defer downloadQueue.Stop()

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.RealIP)

	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "ok")
	})

	r.Mount("/api", api.NewRouter(database, audibleClient, downloadQueue, cfg))
	r.Get("/ws/downloads", api.WSHandler(downloadQueue))

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      otelhttp.NewHandler(r, "web-libation"),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 60 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		log.Printf("server listening on :%s", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("shutting down...")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	srv.Shutdown(shutdownCtx)
}
