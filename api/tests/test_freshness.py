"""Freshness classification, and the thresholds it must share with everything else.

Four places have to agree on what stale means: the copilot's refusal, dbt's
source freshness, Dagster's freshness policies on the marts, and this endpoint.
The API cannot import the others (its image builds from api/ alone), so this is
the test that keeps the repeated constants honest.
"""

import main


def test_thresholds_match_the_copilot_trust_gate():
    from copilot.trust_gate import FRESHNESS_ERROR_HOURS, FRESHNESS_WARN_HOURS

    assert main.FRESHNESS_WARN_HOURS == FRESHNESS_WARN_HOURS == 24
    assert main.FRESHNESS_ERROR_HOURS == FRESHNESS_ERROR_HOURS == 48


def test_fresh_below_the_warn_threshold():
    assert main.classify_age(0) == "fresh"
    assert main.classify_age(23.9) == "fresh"
    assert main.classify_age(24) == "fresh"


def test_warn_between_the_thresholds():
    assert main.classify_age(24.1) == "warn"
    assert main.classify_age(47.9) == "warn"
    assert main.classify_age(48) == "warn"


def test_stale_past_the_error_threshold():
    assert main.classify_age(48.1) == "stale"
    assert main.classify_age(500) == "stale"


def test_never_loaded_is_stale_not_fresh():
    """Absence of data is not evidence of freshness."""
    assert main.classify_age(None) == "stale"


def test_every_raw_source_is_checked():
    names = {name for name, _ in main.FRESHNESS_SOURCES}
    assert names == {"aria_calls", "stripe_payments", "jobs"}


def test_raw_schema_is_quoted_for_redshift():
    for _, table in main.FRESHNESS_SOURCES:
        assert table.startswith('"raw".')
