"""The sensors themselves: do they call the reporting they promise?

test_sensors.py pins the reporting contract. These tests pin the wire from a
finished Dagster run to that contract, so a sensor that silently reported
nothing would still fail a test.
"""

from pathlib import Path

import pytest
from dagster import (
    DagsterEvent,
    DagsterEventType,
    DagsterInstance,
    build_run_status_sensor_context,
)

from orchestration import sensors


@pytest.fixture
def instance():
    with DagsterInstance.ephemeral() as inst:
        yield inst


def _fake_run(instance, *, tags=None, status=None):
    """A finished run to hand the sensors, with no job execution needed."""
    from dagster._core.storage.dagster_run import DagsterRun, DagsterRunStatus

    run = DagsterRun(
        job_name="reckon_full_refresh",
        run_id="00000000-0000-0000-0000-000000000001",
        status=status or DagsterRunStatus.FAILURE,
        tags=tags or {},
    )
    return run


def _failure_event(run):
    return DagsterEvent(
        event_type_value=DagsterEventType.RUN_FAILURE.value,
        job_name=run.job_name,
        message="stripe_payments_raw: source unavailable",
    )


def _success_event(run):
    return DagsterEvent(
        event_type_value=DagsterEventType.RUN_SUCCESS.value,
        job_name=run.job_name,
        message="run succeeded",
    )


def test_failure_sensor_reports_the_failure(instance, monkeypatch):
    reported = {}
    monkeypatch.setattr(
        sensors,
        "push_run_failure",
        lambda reason, dbt_results_path=None: reported.update(
            reason=reason, dbt=dbt_results_path
        ),
    )

    run = _fake_run(instance)
    context = build_run_status_sensor_context(
        sensor_name="reckon_run_failure_sensor",
        dagster_instance=instance,
        dagster_run=run,
        dagster_event=_failure_event(run),
    ).for_run_failure()

    sensors.reckon_run_failure_sensor(context)

    assert "stripe_payments_raw: source unavailable" in reported["reason"]
    assert run.job_name in reported["reason"]
    assert run.run_id in reported["reason"]


def test_success_sensor_reports_a_success(instance, monkeypatch):
    reported = {}
    monkeypatch.setattr(
        sensors,
        "push_run_success",
        lambda duration_seconds, rows_by_source, dbt_results_path=None: reported.update(
            duration=duration_seconds, rows=rows_by_source
        ),
    )

    run = _fake_run(instance)
    context = build_run_status_sensor_context(
        sensor_name="reckon_run_success_sensor",
        dagster_instance=instance,
        dagster_run=run,
        dagster_event=_success_event(run),
    )

    sensors.reckon_run_success_sensor(context)

    assert "rows" in reported, "the success sensor reported nothing"
    assert reported["duration"] >= 0


@pytest.mark.parametrize("outcome", ["failure", "success"])
def test_sensor_skips_a_run_that_reports_its_own_outcome(
    instance, monkeypatch, outcome
):
    def unexpected_push(*args, **kwargs):
        raise AssertionError("self-reported run was pushed by a sensor")

    run = _fake_run(
        instance,
        tags={sensors.SELF_REPORTED_OUTCOME_TAG: "true"},
    )
    context = build_run_status_sensor_context(
        sensor_name=f"reckon_run_{outcome}_sensor",
        dagster_instance=instance,
        dagster_run=run,
        dagster_event=(
            _failure_event(run) if outcome == "failure" else _success_event(run)
        ),
    )

    if outcome == "failure":
        monkeypatch.setattr(sensors, "push_run_failure", unexpected_push)
        sensors.reckon_run_failure_sensor(context.for_run_failure())
    else:
        monkeypatch.setattr(sensors, "push_run_success", unexpected_push)
        sensors.reckon_run_success_sensor(context)


def test_non_daemon_pipeline_marks_runs_as_self_reported():
    script = (
        Path(__file__).parents[2] / "scripts" / "run_pipeline.sh"
    ).read_text()
    assert sensors.SELF_REPORTED_OUTCOME_TAG in script


def test_row_counts_survive_a_run_with_no_materialisations(instance):
    """Reporting must degrade quietly, never take a green run down with it."""

    class Ctx:
        pass

    ctx = Ctx()
    ctx.instance = instance
    assert sensors._rows_by_source(ctx) == {}
