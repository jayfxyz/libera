package telemetry

import (
	"context"
	"log"
	"os"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

// Init initialises the global OTel tracer provider and returns a shutdown function.
// If OTEL_EXPORTER_OTLP_ENDPOINT is not set, tracing is disabled (no-op).
func Init(ctx context.Context) func(context.Context) error {
	if os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT") == "" {
		log.Println("telemetry: OTEL_EXPORTER_OTLP_ENDPOINT not set, tracing disabled")
		return func(context.Context) error { return nil }
	}

	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = "web-libation-backend"
	}

	// otlptracegrpc.New reads OTEL_EXPORTER_OTLP_ENDPOINT automatically
	exporter, err := otlptracegrpc.New(ctx)
	if err != nil {
		log.Printf("telemetry: failed to create OTLP exporter: %v", err)
		return func(context.Context) error { return nil }
	}

	res, _ := resource.New(ctx,
		resource.WithAttributes(semconv.ServiceNameKey.String(serviceName)),
		resource.WithTelemetrySDK(),
		resource.WithHost(),
	)

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
	)

	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	log.Printf("telemetry: OTLP tracing enabled → %s (service=%s)",
		os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"), serviceName)
	return tp.Shutdown
}
