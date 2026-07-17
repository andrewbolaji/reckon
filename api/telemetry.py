"""OpenTelemetry instrumentation for the Reckon API.

Gated on OTEL_ENABLED=true. When disabled, init_telemetry() is a no-op
and no OTel packages are imported.
"""

import os


def init_telemetry(app):
    """Instrument the FastAPI app with OpenTelemetry metrics.

    Must be called BEFORE the app starts serving (before lifespan).
    Exposes metrics on a separate port for Prometheus scraping.
    No-op when OTEL_ENABLED is not 'true'.
    """
    if os.getenv("OTEL_ENABLED", "").lower() != "true":
        return

    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from prometheus_client import start_http_server

    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

    METRICS_PORT = int(os.getenv("METRICS_PORT", "9464"))
    start_http_server(METRICS_PORT)
    print(f"Prometheus metrics exposed on :{METRICS_PORT}/metrics")
