"""Freshness policies on the marts must match the trust gate.

The thresholds are asserted against the copilot's own constants rather than
against literals. If someone loosens the copilot to 72 hours and forgets
Dagster, this fails, which is the whole point: the two must not drift into
disagreeing about what stale means.
"""

from datetime import timedelta

from dagster import AssetKey

from copilot.trust_gate import FRESHNESS_ERROR_HOURS, FRESHNESS_WARN_HOURS
from orchestration.assets_dbt import FRESHNESS_FAIL_HOURS, FRESHNESS_WARN_HOURS as ORCH_WARN
from orchestration.definitions import defs

MART_KEYS = [
    AssetKey(["marts", "mart_call_funnel"]),
    AssetKey(["marts", "mart_revenue"]),
    AssetKey(["marts", "mart_jobs"]),
]

STAGING_KEYS = [
    AssetKey(["staging", "stg_aria_calls"]),
    AssetKey(["staging", "stg_stripe_payments"]),
    AssetKey(["staging", "stg_jobs"]),
]


def test_thresholds_agree_with_the_copilot_trust_gate():
    assert ORCH_WARN == FRESHNESS_WARN_HOURS == 24
    assert FRESHNESS_FAIL_HOURS == FRESHNESS_ERROR_HOURS == 48


def test_every_mart_carries_the_freshness_policy():
    graph = defs.resolve_asset_graph()
    for key in MART_KEYS:
        policy = graph.get(key).freshness_policy
        assert policy is not None, f"{key} has no freshness policy"
        assert policy.fail_window.to_timedelta() == timedelta(hours=48)
        assert policy.warn_window.to_timedelta() == timedelta(hours=24)


def test_staging_models_are_not_given_a_freshness_policy():
    """Staging is an implementation detail; the marts are what people trust."""
    graph = defs.resolve_asset_graph()
    for key in STAGING_KEYS:
        assert graph.get(key).freshness_policy is None
