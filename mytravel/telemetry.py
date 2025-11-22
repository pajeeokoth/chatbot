# mytravel/telemetry.py
import os
import logging
from typing import Optional, Dict

# OpenTelemetry API & SDK
from opentelemetry import trace, metrics
from opentelemetry.trace import TracerProvider
from opentelemetry.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.instrumentation.aiohttp_server import AioHttpServerInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

# Azure monitor configure helper
from azure.monitor.opentelemetry import configure_azure_monitor

# Get a logger
logger = logging.getLogger(__name__)


def init_azure_monitor(connection_string_env: str = "APPLICATIONINSIGHTS_CONNECTION_STRING") -> None:
    """
    Configure OpenTelemetry to export traces and metrics to Azure Monitor.
    Call this early during app startup (create_app).
    """
    conn = os.getenv(connection_string_env) or ""
    if not conn:
        logger.warning("Azure Monitor connection string is not set; telemetry disabled.")
        return

    # Optional: include service name/version for resource tagging
    resource = Resource.create({
        "service.name": os.getenv("AZURE_SERVICE_NAME", "mytravel-bot"),
        "service.version": os.getenv("AZURE_SERVICE_VERSION", "1.0.0"),
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })

    # configure_azure_monitor wires traces/metrics/logs for you
    configure_azure_monitor(connection_string=conn, resource=resource)

    # Instrument aiohttp (server & client), requests, and logging
    try:
        AioHttpServerInstrumentor().instrument()
        AioHttpClientInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        LoggingInstrumentor().instrument(set_logging_format=True)
    except Exception as e:
        logger.exception("Failed to auto-instrument libs: %s", e)

    logger.info("Azure Monitor OpenTelemetry configured")


# ---------------------------
# Helpers for app code
# ---------------------------
_tracer = trace.get_tracer(__name__)
_meter = metrics.get_meter(__name__)


def get_tracer():
    return _tracer


def get_meter():
    return _meter


def track_event(name: str, properties: Optional[Dict] = None) -> None:
    """
    Lightweight helper to record a custom "event" (as a span annotation).
    In Application Insights this surfaces under traces/events.
    """
    props = properties or {}
    with _tracer.start_as_current_span(f"event:{name}") as span:
        for k, v in props.items():
            span.set_attribute(k, v)


def track_metric(name: str, value: float, attributes: Optional[Dict] = None) -> None:
    """
    Record a numeric metric (e.g., CLU latency).
    """
    try:
        meter = get_meter()
        counter = meter.create_observable_gauge(name)  # for simple demo; prefer instruments in real code
        # NOTE: If you want counters/histograms, instantiate proper instruments at module init.
        # For simplicity we emit a span attribute as well:
        with _tracer.start_as_current_span(f"metric:{name}") as span:
            span.set_attribute("metric.value", value)
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
    except Exception:
        logger.exception("track_metric failed")


def track_dependency(name: str, data: str, success: bool = True, duration_ms: Optional[int] = None, properties: Optional[Dict] = None):
    """
    Record a dependency (e.g., CLU API call). Creates a child span labeled as a dependency.
    """
    attrs = properties or {}
    attrs["dependency.name"] = name
    attrs["dependency.data"] = data
    attrs["dependency.success"] = success
    if duration_ms is not None:
        attrs["dependency.duration_ms"] = duration_ms

    with _tracer.start_as_current_span(f"dep:{name}") as span:
        for k, v in attrs.items():
            span.set_attribute(k, v)
        if not success:
            span.set_status(trace.Status(trace.StatusCode.ERROR, description=str(data)))
