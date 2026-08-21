"""Pipeline metrics for Prometheus via Pushgateway.

Gated on OTEL_ENABLED=true. All pushes are non-fatal: if the Pushgateway
is unreachable or OTEL is disabled, the pipeline still succeeds.

Orchestration reports through here too, so a Dagster run failure reaches the
same Prometheus and the same Alertmanager as everything else rather than
growing a second alerting story. Pushes use POST (``pushadd_to_gateway``), not
PUT, and the distinction is load-bearing: a PUT replaces every metric in the
job's group, so a failure push would wipe ``pipeline_last_success_timestamp``
and quietly disarm PipelineFreshnessBreach. With POST, the last success stands
and keeps ageing while runs fail, which is exactly what should trip that alert.
"""

import json
import os
import time
from pathlib import Path

PUSH_JOB = "reckon_pipeline"
PUSH_TIMEOUT = 5  # seconds


def _pushgateway_url():
    return os.getenv("PUSHGATEWAY_URL", "http://pushgateway:9091")


def _enabled():
    return os.getenv("OTEL_ENABLED", "").lower() == "true"


def push_pipeline_metrics(
    duration_seconds: float,
    rows_by_source: dict[str, int],
    dbt_results_path: str | None = None,
):
    """Push metrics for a successful pipeline run. See ``push_run_success``."""
    push_run_success(duration_seconds, rows_by_source, dbt_results_path)


def push_run_success(
    duration_seconds: float,
    rows_by_source: dict[str, int],
    dbt_results_path: str | None = None,
):
    """Push metrics for a successful run to the Prometheus Pushgateway.

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
        _do_push_success(duration_seconds, rows_by_source, dbt_results_path)
    except Exception as e:
        print(f"[telemetry] Metrics push failed (non-fatal): {e}")


def push_run_failure(reason: str, dbt_results_path: str | None = None):
    """Push metrics for a failed run.

    Deliberately does not touch ``pipeline_last_success_timestamp``: a run that
    fails did not succeed, and letting that timestamp age is how a pipeline
    stuck failing eventually trips PipelineFreshnessBreach on its own.

    The reason is logged rather than made a metric label. Free text in a label
    means unbounded cardinality, and a label that changes every failure never
    resolves cleanly in Alertmanager.
    """
    print(
        "[telemetry] "
        + json.dumps({"event": "pipeline_run_failed", "reason": reason})
    )
    if not _enabled():
        return

    try:
        _do_push_failure(dbt_results_path)
    except Exception as e:
        print(f"[telemetry] Metrics push failed (non-fatal): {e}")


def _push(registry):
    from prometheus_client import pushadd_to_gateway

    url = _pushgateway_url()
    pushadd_to_gateway(url, job=PUSH_JOB, registry=registry, timeout=PUSH_TIMEOUT)
    print(f"[telemetry] Metrics pushed to {url}")


def _run_failed_gauge(registry):
    from prometheus_client import Gauge

    return Gauge(
        "pipeline_run_failed",
        "1 if the most recent pipeline run failed, 0 if it succeeded",
        registry=registry,
    )


def _dbt_results_gauge(registry, dbt_results_path: str | None):
    from prometheus_client import Gauge

    gauge = Gauge(
        "pipeline_dbt_test_results",
        "Count of dbt test results by status",
        ["status"],
        registry=registry,
    )
    for status, count in _parse_dbt_results(dbt_results_path).items():
        gauge.labels(status=status).set(count)
    return gauge


def _do_push_success(
    duration_seconds: float,
    rows_by_source: dict[str, int],
    dbt_results_path: str | None,
):
    from prometheus_client import CollectorRegistry, Gauge

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

    # Only report dbt results when this reporter can see the run's artifact.
    # Absence means "unknown here", not "the run executed zero tests".
    if dbt_results_path:
        _dbt_results_gauge(registry, dbt_results_path)

    # Clear any standing failure so PipelineRunFailure resolves.
    _run_failed_gauge(registry).set(0)

    _push(registry)


def _do_push_failure(dbt_results_path: str | None):
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    _run_failed_gauge(registry).set(1)
    # Only report dbt results if the run actually got that far. Pushing zeroes
    # for a run that died during ingest would erase the previous run's real
    # test counts and silence PipelineDbtTestFailure.
    if dbt_results_path:
        _dbt_results_gauge(registry, dbt_results_path)
    _push(registry)


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
