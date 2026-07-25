"""The source assets: retries, windows, and the failure mode.

The break tests are the demo's failure mode under test. That failure is the
reason the orchestration is worth having, so it should not be something only a
screenshot proves.

Behaviour is exercised through ``build_ingest_asset``, the same factory that
builds the real three, with a stub source rather than a live warehouse. The
policies on the real assets are asserted directly.
"""

from dataclasses import replace
from datetime import date

from dagster import AssetKey, Backoff, Jitter, asset, materialize

from orchestration import assets_ingest
from orchestration.assets_ingest import (
    BREAK_ENV_VAR,
    SOURCE_SPECS,
    SourceSpec,
    broken_sources,
    build_ingest_asset,
    ingest_assets,
)
from orchestration.definitions import defs
from orchestration.partitions import full_window

WINDOW_START, WINDOW_END = full_window()
A_PARTITION = "2026-07-02"


# --- Retries -----------------------------------------------------------


def test_every_ingest_asset_retries_with_exponential_backoff():
    for asset_def in ingest_assets:
        policy = asset_def.op.retry_policy
        assert policy is not None
        assert policy.max_retries == 3
        assert policy.delay == 2
        assert policy.backoff == Backoff.EXPONENTIAL
        assert policy.jitter == Jitter.PLUS_MINUS


def test_dbt_assets_do_not_retry():
    """A dbt failure is usually a failing test, and retrying a failing test is
    just a slower way to fail."""
    dbt_asset = next(
        a for a in defs.assets if AssetKey(["marts", "mart_revenue"]) in a.keys
    )
    assert dbt_asset.op.retry_policy is None


# --- Partitioning ------------------------------------------------------


def test_ingest_assets_are_daily_partitioned_over_the_demo_window():
    for asset_def in ingest_assets:
        keys = asset_def.partitions_def.get_partition_keys()
        assert WINDOW_START in keys
        assert WINDOW_END in keys


def test_ingest_assets_backfill_a_range_in_one_run():
    """`--partition-range` requires a single-run backfill policy, and that is
    what turns a week-long backfill into one command instead of seven."""
    for asset_def in ingest_assets:
        policy = asset_def.backfill_policy
        assert policy is not None
        assert policy.max_partitions_per_run is None, "expected single_run()"


# --- Windowing ---------------------------------------------------------


def _stub_spec(name="stub_source_raw", **overrides) -> SourceSpec:
    """A SourceSpec whose extract records its arguments instead of doing work."""
    calls: dict = {}

    def fake_extract(lake, window):
        calls["window"] = window
        return "lake://stub"

    spec = SourceSpec(
        asset_name=name,
        lake_source="stub",
        raw_table="stub",
        columns=["a"],
        date_column="ts",
        description="stub",
        extract=fake_extract,
    )
    spec = replace(spec, **overrides) if overrides else spec
    return spec, calls


def _stub_warehouse_env(monkeypatch):
    for key, value in {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "reckon",
        "POSTGRES_USER": "reckon",
        "POSTGRES_PASSWORD": "reckon_dev",
        "DATA_LAKE_TYPE": "local",
    }.items():
        monkeypatch.setenv(key, value)


def test_asset_passes_its_partition_window_through_to_extract_and_load(monkeypatch):
    """A partition must load only its own days, or a backfill is a full reload."""
    _stub_warehouse_env(monkeypatch)
    spec, calls = _stub_spec()

    loaded = {}

    def fake_load(lake, wh, source, table, columns, window=None, date_column=None):
        loaded.update(window=window, date_column=date_column, table=table)
        return 7

    monkeypatch.setattr(assets_ingest, "load_to_warehouse", fake_load)

    result = materialize([build_ingest_asset(spec)], partition_key=A_PARTITION)

    assert result.success
    assert calls["window"] == loaded["window"], "extract and load must share a window"
    assert loaded["window"].days() == [date(2026, 7, 2)]
    assert loaded["date_column"] == spec.date_column
    assert loaded["table"] == spec.raw_table


def test_asset_reports_rows_and_window_as_metadata(monkeypatch):
    _stub_warehouse_env(monkeypatch)
    spec, _ = _stub_spec()
    monkeypatch.setattr(assets_ingest, "load_to_warehouse", lambda *a, **k: 7)

    result = materialize([build_ingest_asset(spec)], partition_key=A_PARTITION)

    metadata = result.asset_materializations_for_node(spec.asset_name)[0].metadata
    assert metadata["rows_loaded"].value == 7
    assert metadata["window"].value == "2026-07-02..2026-07-02"
    assert metadata["days"].value == 1


def test_a_range_backfill_becomes_one_window(monkeypatch):
    """The single-run backfill policy means one run covers the whole range."""
    _stub_warehouse_env(monkeypatch)
    spec, calls = _stub_spec()
    monkeypatch.setattr(assets_ingest, "load_to_warehouse", lambda *a, **k: 0)

    result = materialize(
        [build_ingest_asset(spec)],
        tags={
            "dagster/asset_partition_range_start": "2026-07-01",
            "dagster/asset_partition_range_end": "2026-07-07",
        },
    )

    assert result.success
    window = calls["window"]
    assert (window.start_iso, window.end_iso) == ("2026-07-01", "2026-07-07")
    assert len(window.days()) == 7, "the end day must be included, not dropped"


# --- The demo's failure mode -------------------------------------------


def test_no_sources_are_broken_by_default():
    assert broken_sources() == set()


def test_break_env_var_selects_sources(monkeypatch):
    monkeypatch.setenv(BREAK_ENV_VAR, "stripe_payments_raw, aria_calls_raw")
    assert broken_sources() == {"stripe_payments_raw", "aria_calls_raw"}


def test_every_real_source_can_be_broken_by_name():
    """The README tells operators to name an asset; every name must work."""
    for spec in SOURCE_SPECS:
        assert spec.asset_name in {s.asset_name for s in SOURCE_SPECS}


def test_broken_source_fails_before_it_touches_the_warehouse(monkeypatch):
    """The break must fire ahead of extract and load, so a demo run cannot
    half-write a partition."""
    _stub_warehouse_env(monkeypatch)
    spec, calls = _stub_spec(name="breakable_raw")
    monkeypatch.setenv(BREAK_ENV_VAR, spec.asset_name)

    def explode(*args, **kwargs):
        raise AssertionError("load must not run for a broken source")

    monkeypatch.setattr(assets_ingest, "load_to_warehouse", explode)

    # Retries are asserted separately; disabling them here keeps the test fast.
    result = materialize(
        [build_ingest_asset(spec, retry_policy=None)],
        partition_key=A_PARTITION,
        raise_on_error=False,
    )

    assert not result.success
    # Dagster wraps the user exception, so the reason lives on the cause.
    cause = result.failure_data_for_node(spec.asset_name).error.cause
    assert cause.cls_name == "RuntimeError"
    assert "source unavailable" in cause.message
    assert "window" not in calls, "extract must not have run"


def test_broken_source_stops_its_downstream_models(monkeypatch):
    """Halting downstream is the whole point of orchestrating this.

    A stub stands in for the dbt models so this needs no warehouse.
    test_definitions.py proves the real staging models sit in that position.
    """
    _stub_warehouse_env(monkeypatch)
    spec, _ = _stub_spec(name="breakable_raw")
    monkeypatch.setenv(BREAK_ENV_VAR, spec.asset_name)
    monkeypatch.setattr(assets_ingest, "load_to_warehouse", lambda *a, **k: 0)

    downstream_ran = []

    @asset(name="downstream_model", deps=[AssetKey(spec.asset_name)])
    def downstream_model():
        downstream_ran.append(True)

    result = materialize(
        [build_ingest_asset(spec, retry_policy=None), downstream_model],
        partition_key=A_PARTITION,
        raise_on_error=False,
    )

    assert not result.success
    assert downstream_ran == [], "downstream ran despite its source failing"
    assert result.asset_materializations_for_node("downstream_model") == []


def test_healthy_source_lets_downstream_run(monkeypatch):
    """The control for the test above: without the break, downstream proceeds."""
    _stub_warehouse_env(monkeypatch)
    spec, _ = _stub_spec(name="breakable_raw")
    monkeypatch.setattr(assets_ingest, "load_to_warehouse", lambda *a, **k: 3)

    downstream_ran = []

    @asset(name="downstream_model", deps=[AssetKey(spec.asset_name)])
    def downstream_model():
        downstream_ran.append(True)

    result = materialize(
        [build_ingest_asset(spec), downstream_model],
        partition_key=A_PARTITION,
    )

    assert result.success
    assert downstream_ran == [True]
