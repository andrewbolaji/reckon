"""Run outcome sensors: orchestration reporting into the existing alerting.

There is no second monitoring stack here. Both sensors push to the same
Prometheus Pushgateway the pipeline has always used (``ingest/telemetry.py``),
so the same Prometheus rules and the same Alertmanager email receiver cover a
Dagster run failure and a pipeline that has simply stopped running.

The asymmetry between the two is the point: only success moves
``pipeline_last_success_timestamp``. A run that keeps failing therefore trips
PipelineRunFailure immediately and PipelineFreshnessBreach on its own once the
last real success passes 48 hours old.
"""

from dagster import (
    DagsterRunStatus,
    DefaultSensorStatus,
    RunFailureSensorContext,
    RunStatusSensorContext,
    run_failure_sensor,
    run_status_sensor,
)

from ingest.telemetry import push_run_failure, push_run_success
from orchestration.assets_ingest import SOURCE_SPECS
from orchestration.resources import DBT_RUN_RESULTS


def _dbt_results_path() -> str | None:
    """dbt's run_results.json, if this run got far enough to write one."""
    return str(DBT_RUN_RESULTS) if DBT_RUN_RESULTS.exists() else None


def _rows_by_source(context) -> dict[str, int]:
    """Row counts from the assets' own materialisation metadata.

    Read back from the event log rather than re-queried from the warehouse: the
    assets already reported what they loaded, and asking the warehouse again
    would report whatever is there now, not what this run put there.
    """
    rows: dict[str, int] = {}
    for spec in SOURCE_SPECS:
        try:
            event = context.instance.get_latest_materialization_event(
                spec.asset_name
            )
            metadata = event.asset_materialization.metadata if event else {}
            value = metadata.get("rows_loaded")
            if value is not None:
                rows[spec.raw_table] = int(value.value)
        except Exception:  # noqa: BLE001 - telemetry must never break the sensor
            continue
    return rows


def _duration_seconds(context) -> float:
    try:
        stats = context.instance.get_run_stats(context.dagster_run.run_id)
        if stats.start_time and stats.end_time:
            return stats.end_time - stats.start_time
    except Exception:  # noqa: BLE001
        pass
    return 0.0


@run_failure_sensor(
    name="reckon_run_failure_sensor",
    description="Push a failed run to the Pushgateway so the existing alerts fire.",
    default_status=DefaultSensorStatus.RUNNING,
    # Without this, a run only matches if its recorded origin's code location
    # and repository name exactly equal the sensor's own, which a run started
    # by `dagster job execute`/`job launch` from the CLI does not always carry.
    # Discovered live running the broken-source demo: the sensor's cursor
    # advanced past every failed run (proving it saw them) while never once
    # invoking this function, because none of them matched on origin.
    # RECKON_BREAK_SOURCE exists to prove failures reach the alert; a sensor
    # that only notices failures launched a specific way is not that.
    monitor_all_code_locations=True,
)
def reckon_run_failure_sensor(context: RunFailureSensorContext):
    run = context.dagster_run
    message = (context.failure_event.message or "").strip()
    reason = f"{run.job_name} run {run.run_id} failed: {message}" if message else (
        f"{run.job_name} run {run.run_id} failed"
    )
    context.log.error(reason)
    push_run_failure(reason, dbt_results_path=_dbt_results_path())


@run_status_sensor(
    name="reckon_run_success_sensor",
    run_status=DagsterRunStatus.SUCCESS,
    description="Push a successful run's freshness, row counts, and dbt results.",
    default_status=DefaultSensorStatus.RUNNING,
    monitor_all_code_locations=True,
)
def reckon_run_success_sensor(context: RunStatusSensorContext):
    push_run_success(
        duration_seconds=_duration_seconds(context),
        rows_by_source=_rows_by_source(context),
        dbt_results_path=_dbt_results_path(),
    )
    context.log.info("Pushed successful run metrics to the Pushgateway.")


all_sensors = [reckon_run_failure_sensor, reckon_run_success_sensor]
