"""The graph is one graph, and it loads.

These are the tests that would have caught the failure this phase exists to
prevent: dbt sources that are their own disconnected nodes, so a dead extract
lets the marts rebuild anyway.
"""

from dagster import AssetKey

from orchestration.assets_ingest import SOURCE_SPECS
from orchestration.definitions import defs

INGEST_KEYS = {AssetKey(spec.asset_name) for spec in SOURCE_SPECS}

STAGING_TO_SOURCE = {
    AssetKey(["staging", "stg_aria_calls"]): AssetKey("aria_calls_raw"),
    AssetKey(["staging", "stg_stripe_payments"]): AssetKey("stripe_payments_raw"),
    AssetKey(["staging", "stg_jobs"]): AssetKey("mongo_jobs_raw"),
}

MART_KEYS = {
    AssetKey(["marts", "mart_call_funnel"]),
    AssetKey(["marts", "mart_revenue"]),
    AssetKey(["marts", "mart_jobs"]),
}


def asset_graph():
    return defs.resolve_asset_graph()


def test_definitions_load():
    """The same thing `dagster definitions validate` gates in CI."""
    assert defs.resolve_all_job_defs()


def test_every_source_and_model_is_an_asset():
    keys = asset_graph().get_all_asset_keys()
    assert INGEST_KEYS <= keys
    assert set(STAGING_TO_SOURCE) <= keys
    assert MART_KEYS <= keys


def test_staging_models_depend_on_the_ingest_assets():
    """The wiring that makes ingest and dbt one DAG rather than two.

    If dagster-dbt's default source keys ever win here, the staging models would
    depend on standalone `raw/*` nodes and a failed extract would no longer stop
    anything downstream.
    """
    graph = asset_graph()
    for staging_key, source_key in STAGING_TO_SOURCE.items():
        assert graph.get(staging_key).parent_keys == {source_key}


def test_no_orphan_dbt_source_assets_remain():
    keys = asset_graph().get_all_asset_keys()
    orphans = {k for k in keys if k.path[0] == "raw"}
    assert not orphans, f"dbt sources not mapped onto ingest assets: {orphans}"


def test_marts_are_downstream_of_ingest():
    """Every mart must trace back to at least one source asset."""
    graph = asset_graph()
    for mart in MART_KEYS:
        upstream = graph.upstream_key_iterator(mart)
        assert INGEST_KEYS & set(upstream), f"{mart} is not fed by any source"


def test_dbt_tests_load_as_asset_checks():
    """The trust gate rides along: dbt's tests are checks on these assets."""
    assert asset_graph().asset_check_keys


def test_jobs_and_schedule_are_defined():
    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert {"reckon_full_refresh", "reckon_ingest_backfill"} <= job_names

    schedules = defs.get_repository_def().schedule_defs
    assert len(schedules) == 1, "one schedule materialises the whole DAG"
    assert schedules[0].name == "reckon_daily_schedule"
    assert schedules[0].job.name == "reckon_full_refresh"


def test_full_refresh_job_covers_the_whole_dag():
    job = defs.resolve_job_def("reckon_full_refresh")
    selected = job.asset_layer.selected_asset_keys
    assert INGEST_KEYS <= selected
    assert MART_KEYS <= selected


def test_backfill_job_is_ingest_only():
    job = defs.resolve_job_def("reckon_ingest_backfill")
    selected = job.asset_layer.selected_asset_keys
    assert selected == INGEST_KEYS


def test_sensors_are_registered():
    names = {s.name for s in defs.get_repository_def().sensor_defs}
    assert {"reckon_run_failure_sensor", "reckon_run_success_sensor"} <= names
