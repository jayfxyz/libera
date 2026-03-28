import logging
import os
logging.basicConfig(level=logging.INFO)


def _init_telemetry():
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    service_name = os.environ.get("OTEL_SERVICE_NAME", "audible-svc")
    if not endpoint:
        logging.getLogger(__name__).info("OTEL_EXPORTER_OTLP_ENDPOINT not set, tracing disabled")
        return
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    logging.getLogger(__name__).info("OTel tracing enabled → %s (service=%s)", endpoint, service_name)


_init_telemetry()

from fastapi import FastAPI
from routes.auth import router as auth_router
from routes.library import router as library_router
from routes.download import router as download_router

app = FastAPI(title="audible-svc", docs_url=None, redoc_url=None)

# Instrument FastAPI — must be called after app creation
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()

app.include_router(auth_router, prefix="/auth")
app.include_router(library_router, prefix="/library")
app.include_router(download_router, prefix="/download")


@app.get("/health")
def health():
    return {"status": "ok"}
