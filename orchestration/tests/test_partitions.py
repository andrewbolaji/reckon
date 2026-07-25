"""The partition window must cover the data the extractors actually produce.

This is the test for a failure that is invisible from the outside: if the window
starts a day late, a full run still goes green and the marts are simply short a
few records. The first version of this window did exactly that, dropping two
calls, and nothing complained.
"""

import json
from datetime import date, timedelta

from orchestration.partitions import (
    REFERENCE_DATE,
    WINDOW_START,
    daily_partitions,
    full_window,
)
from ingest.extractors.aria_calls import generate_call_records
from ingest.extractors.stripe_payments import generate_payment_records
from orchestration.resources import REPO_ROOT

SEED_JOBS = REPO_ROOT / "mongo" / "init" / "seed_jobs.json"


def window_covers(timestamps) -> bool:
    start, end = full_window()
    return all(start <= ts[:10] <= end for ts in timestamps)


def test_window_starts_before_the_earliest_generated_record():
    earliest = min(
        min(r["timestamp"] for r in generate_call_records(200)),
        min(r["timestamp"] for r in generate_payment_records(150)),
    )
    assert WINDOW_START.isoformat() <= earliest[:10], (
        "the window starts after the data does, so a full run would silently "
        "drop the earliest records"
    )


def test_full_window_covers_every_call_and_payment():
    """Aria and Stripe events are all in the past, so all of them must load."""
    assert window_covers(r["timestamp"] for r in generate_call_records(200))
    assert window_covers(r["timestamp"] for r in generate_payment_records(150))


def test_jobs_outside_the_window_are_future_bookings_not_lost_history():
    """The jobs source partitions on scheduled_at, which looks forward.

    Anything the window excludes must be scheduled beyond the present edge, not
    history that fell off the back.
    """
    _, end = full_window()
    jobs = json.loads(SEED_JOBS.read_text())
    excluded = [j["scheduled_at"][:10] for j in jobs if j["scheduled_at"][:10] > end]
    assert all(day > end for day in excluded)
    assert not [j for j in jobs if j["scheduled_at"][:10] < WINDOW_START.isoformat()]


def test_window_end_is_a_real_partition():
    """A window end Dagster has no partition for cannot be materialised."""
    _, end = full_window()
    assert end in daily_partitions.get_partition_keys()


def test_window_never_reaches_into_the_future():
    _, end = full_window()
    assert date.fromisoformat(end) < date.today() + timedelta(days=1)


def test_window_start_is_anchored_to_the_reference_date_not_the_clock():
    """So the earliest partition is the same on any machine, on any day."""
    assert WINDOW_START == (REFERENCE_DATE - timedelta(days=31)).date()
