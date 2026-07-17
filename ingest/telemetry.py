"""Pipeline metrics for Prometheus via Pushgateway.

Gated on OTEL_ENABLED=true. All pushes are non-fatal: if the Pushgateway
is unreachable or OTEL is disabled, the pipeline still succeeds.
"""

import json
import os
import time
from pathlib import Path


def _pushgateway_url():
    return os.getenv("PUSHGATEWAY_URL", "http://pushgateway:9091")


def _enabled():
    return os.getenv("OTEL_ENABLED", "").lower() == "true"


def push_pipeline_metrics(
    duration_seconds: float,
    rows_by_source: dict[str, int],
    dbt_results_path: str | None = None,
):
    """Push pipeline run metrics to the Prometheus Pushgateway.

    Non-fatal: swallows all exceptions with a log line. The pipeline
    must never fail because observability is unavailable.

    Args:
        duration_seconds: Wall-clock time for the full pipeline run.
        rows_by_source: {"aria_calls": N, "stripe_payments": N, "jobs": N}
        dbt_results_path: Path to dbt's target/run_results.json artifact.
    """
    if not _enabled():
        return

    try:
        _do_push(duration_seconds, rows_by_source, dbt_results_path)
    except Exception as e:
        print(f"[telemetry] Metrics push failed (non-fatal): {e}")


def _do_push(
    duration_seconds: float,
    rows_by_source: dict[str, int],
    dbt_results_path: str | None,
):
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        push_to_gateway,
    )

    registry = CollectorRegistry()

    # Pipeline run duration
    duration = Gauge(
        "pipeline_run_duration_seconds",
        "Wall-clock duration of the last pipeline run",
        registry=registry,
    )
    duration.set(duration_seconds)

    # Last success timestamp
    last_success = Gauge(
        "pipeline_last_success_timestamp",
        "Unix timestamp of the last successful pipeline run",
        registry=registry,
    )
    last_success.set(time.time())

    # Rows loaded per source
    rows_gauge = Gauge(
        "pipeline_rows_loaded",
        "Number of rows loaded per source",
        ["source"],
        registry=registry,
    )
    for source, count in rows_by_source.items():
        rows_gauge.labels(source=source).set(count)

    # dbt test results from run_results.json
    dbt_gauge = Gauge(
        "pipeline_dbt_test_results",
        "Count of dbt test results by status",
        ["status"],
        registry=registry,
    )
    dbt_counts = _parse_dbt_results(dbt_results_path)
    for status, count in dbt_counts.items():
        dbt_gauge.labels(status=status).set(count)

    url = _pushgateway_url()
    PUSH_TIMEOUT = 5  # seconds
    push_to_gateway(url, job="reckon_pipeline", registry=registry, timeout=PUSH_TIMEOUT)
    print(f"[telemetry] Metrics pushed to {url}")


def _parse_dbt_results(path: str | None) -> dict[str, int]:
    """Parse dbt's target/run_results.json for test pass/fail/error counts.

    Returns {"pass": N, "fail": N, "error": N, "warn": N, "skip": N}.
    Falls back to zeroes if the file is missing or unparseable.
    """
    counts = {"pass": 0, "fail": 0, "error": 0, "warn": 0, "skip": 0}
    if not path:
        return counts

    try:
        data = json.loads(Path(path).read_text())
        for result in data.get("results", []):
            status = result.get("status", "unknown")
            if status in counts:
                counts[status] += 1
    except Exception as e:
        print(f"[telemetry] Could not parse dbt results at {path}: {e}")

    return counts
