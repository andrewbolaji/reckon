"""Run outcome reporting: the wire between orchestration and alerting.

The asymmetry these tests pin down is the important part. Only a success may
move ``pipeline_last_success_timestamp``. If a failure moved it too, a pipeline
stuck failing would look permanently fresh and PipelineFreshnessBreach would
never fire, which is the quiet failure mode worth a test.
"""

import json

import pytest

from ingest import telemetry


class FakeGateway:
    """Captures what would have been pushed, per metric name."""

    def __init__(self):
        self.pushed: dict[str, float] = {}
        self.push_count = 0
        self.method = None

    def install(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        gateway = self

        def fake_pushadd(url, job, registry, timeout=None):
            gateway.push_count += 1
            gateway.method = "pushadd"
            for metric in registry.collect():
                for sample in metric.samples:
                    key = sample.name
                    if sample.labels:
                        labels = ",".join(f"{k}={v}" for k, v in sorted(sample.labels.items()))
                        key = f"{sample.name}{{{labels}}}"
                    gateway.pushed[key] = sample.value

        import prometheus_client

        monkeypatch.setattr(prometheus_client, "pushadd_to_gateway", fake_pushadd)
        return gateway


@pytest.fixture
def gateway(monkeypatch):
    return FakeGateway().install(monkeypatch)


def test_success_push_records_freshness_and_rows(gateway):
    telemetry.push_run_success(
        duration_seconds=12.5,
        rows_by_source={"aria_calls": 200, "jobs": 83},
    )
    assert gateway.push_count == 1
    assert gateway.pushed["pipeline_run_duration_seconds"] == 12.5
    assert gateway.pushed["pipeline_last_success_timestamp"] > 0
    assert gateway.pushed["pipeline_rows_loaded{source=aria_calls}"] == 200
    assert gateway.pushed["pipeline_rows_loaded{source=jobs}"] == 83


def test_success_push_clears_a_standing_failure(gateway):
    """So PipelineRunFailure resolves once a run goes green again."""
    telemetry.push_run_success(duration_seconds=1, rows_by_source={})
    assert gateway.pushed["pipeline_run_failed"] == 0


def test_success_without_dbt_artifact_does_not_emit_false_zeroes(gateway):
    """An artifact absent from this reporter is unknown, not zero tests.

    A direct CLI run and an always-on sensor may live in different containers.
    If the sensor cannot see the CLI container's dbt artifact, it must preserve
    the real counts already pushed by the run instead of replacing them with
    zeroes.
    """
    telemetry.push_run_success(duration_seconds=1, rows_by_source={})
    assert not any(
        key.startswith("pipeline_dbt_test_results")
        for key in gateway.pushed
    )


def test_failure_push_raises_the_failure_flag(gateway):
    telemetry.push_run_failure("aria_calls_raw: source unavailable")
    assert gateway.pushed["pipeline_run_failed"] == 1


def test_failure_push_never_touches_the_last_success_timestamp(gateway):
    """The load-bearing asymmetry: a failed run did not succeed.

    Letting that timestamp stand and age is how a pipeline stuck failing trips
    PipelineFreshnessBreach on its own.
    """
    telemetry.push_run_failure("boom")
    assert "pipeline_last_success_timestamp" not in gateway.pushed


def test_failure_push_does_not_erase_earlier_dbt_results(gateway):
    """A run that died during ingest has no dbt results of its own.

    Pushing zeroes would wipe the previous run's real test counts and silence
    PipelineDbtTestFailure.
    """
    telemetry.push_run_failure("died during ingest")
    assert not any(k.startswith("pipeline_dbt_test_results") for k in gateway.pushed)


def test_failure_push_reports_dbt_results_when_the_run_got_that_far(gateway, tmp_path):
    results = tmp_path / "run_results.json"
    results.write_text(json.dumps({"results": [
        {"status": "pass"}, {"status": "fail"}, {"status": "fail"},
    ]}))

    telemetry.push_run_failure("dbt build failed", dbt_results_path=str(results))

    assert gateway.pushed["pipeline_dbt_test_results{status=fail}"] == 2
    assert gateway.pushed["pipeline_dbt_test_results{status=pass}"] == 1


def test_pushes_use_post_so_they_do_not_wipe_the_group(gateway):
    """PUT replaces every metric in the Pushgateway group. A failure push using
    PUT would delete pipeline_last_success_timestamp and disarm the freshness
    alert, so this must stay a POST."""
    telemetry.push_run_failure("boom")
    assert gateway.method == "pushadd"


def test_nothing_is_pushed_when_telemetry_is_disabled(monkeypatch):
    gateway = FakeGateway().install(monkeypatch)
    monkeypatch.setenv("OTEL_ENABLED", "false")

    telemetry.push_run_success(duration_seconds=1, rows_by_source={})
    telemetry.push_run_failure("boom")

    assert gateway.push_count == 0


def test_reporting_failures_never_break_the_run(monkeypatch, capsys):
    """Observability being down must not turn a green run red."""
    monkeypatch.setenv("OTEL_ENABLED", "true")
    import prometheus_client

    def unreachable(*args, **kwargs):
        raise ConnectionError("pushgateway unreachable")

    monkeypatch.setattr(prometheus_client, "pushadd_to_gateway", unreachable)

    telemetry.push_run_success(duration_seconds=1, rows_by_source={})
    telemetry.push_run_failure("boom")

    assert "non-fatal" in capsys.readouterr().out


def test_failure_reason_is_logged_not_made_a_metric_label(gateway, capsys):
    """Free text in a label is unbounded cardinality and never resolves cleanly."""
    telemetry.push_run_failure("stripe_payments_raw: source unavailable")

    logged = capsys.readouterr().out
    assert "pipeline_run_failed" in logged
    assert "stripe_payments_raw: source unavailable" in logged
    assert all("reason" not in key for key in gateway.pushed)


def test_legacy_entrypoint_still_reports_a_success(gateway):
    """push_pipeline_metrics is what the pre-Dagster script called."""
    telemetry.push_pipeline_metrics(3.0, {"aria_calls": 5})
    assert gateway.pushed["pipeline_last_success_timestamp"] > 0
    assert gateway.pushed["pipeline_rows_loaded{source=aria_calls}"] == 5


def test_run_outcome_sensors_are_on_by_default():
    """A sensor Dagster defines but never starts never gets evaluated.

    Both sensors are defined with no ``default_status``, which is
    ``DefaultSensorStatus.STOPPED``: the daemon evaluates a stopped sensor
    only after someone flips it on in the UI. Without this, a fresh
    deployment's first failure never reaches the Pushgateway, and the
    failure wiring silently does nothing until someone notices and clicks
    a toggle. Discovered live: the broken-source demo pushed
    ``pipeline_run_failed`` only after this was turned on by default.
    """
    from dagster import DefaultSensorStatus

    from orchestration.sensors import all_sensors

    for sensor in all_sensors:
        assert sensor.default_status == DefaultSensorStatus.RUNNING, sensor.name


def test_run_outcome_sensors_monitor_every_code_location():
    """Without this, a sensor only matches runs whose recorded origin exactly

    equals its own code location and repository name. A run started via
    `dagster job execute` or `job launch` from the CLI, rather than launched
    by the webserver from the loaded workspace, does not reliably carry that
    match. Discovered live: the broken-source demo's sensor cursor advanced
    past every failed run (proof it saw them) while never once calling the
    decorated function, because none of them matched on origin. A sensor
    that only notices failures launched one specific way is not the failure
    wiring this project claims to have.
    """
    from orchestration.sensors import all_sensors

    for sensor in all_sensors:
        assert sensor._monitor_all_code_locations, sensor.name  # noqa: SLF001


def test_daily_schedule_is_on_by_default():
    """Same failure mode as the sensors: an unstarted schedule never ticks.

    This is what replaces the old cron entry, so it needs to run without a
    manual step the same way the cron entry did.
    """
    from dagster import DefaultScheduleStatus

    from orchestration.schedules import reckon_daily_schedule

    assert reckon_daily_schedule.default_status == DefaultScheduleStatus.RUNNING
