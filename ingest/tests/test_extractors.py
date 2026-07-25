"""Unit tests for the extractors."""

from ingest.config import LakeConfig
from ingest.extractors import aria_calls, mongo_jobs, stripe_payments
from ingest.extractors.aria_calls import generate_call_records
from ingest.extractors.stripe_payments import generate_payment_records
from ingest.lake import read_raw
from ingest.window import DateWindow


def test_aria_generates_correct_count():
    records = generate_call_records(n=50)
    assert len(records) == 50


def test_aria_record_fields():
    records = generate_call_records(n=1)
    r = records[0]
    assert "call_id" in r
    assert "timestamp" in r
    assert r["urgency"] in ("low", "medium", "high", "critical")
    assert r["outcome"] in ("booked", "qualified", "escalated", "missed", "resolved")
    assert isinstance(r["duration_seconds"], int)
    assert r["duration_seconds"] > 0


def test_aria_records_sorted_by_timestamp():
    records = generate_call_records(n=20)
    timestamps = [r["timestamp"] for r in records]
    assert timestamps == sorted(timestamps)


def test_aria_deterministic_with_same_seed():
    a = generate_call_records(n=10, seed=42)
    b = generate_call_records(n=10, seed=42)
    assert [r["call_id"] for r in a] == [r["call_id"] for r in b]


def test_aria_different_seeds_differ():
    a = generate_call_records(n=10, seed=42)
    b = generate_call_records(n=10, seed=99)
    assert [r["call_id"] for r in a] != [r["call_id"] for r in b]


def test_stripe_generates_records():
    records = generate_payment_records(n=50)
    assert len(records) > 0  # some may be skipped (estimate-only services)


def test_stripe_record_fields():
    records = generate_payment_records(n=50)
    r = records[0]
    assert "payment_id" in r
    assert r["payment_id"].startswith("pi_")
    assert "amount_cents" in r
    assert isinstance(r["amount_cents"], int)
    assert r["amount_cents"] > 0
    assert r["status"] in ("succeeded", "refunded", "failed")


def test_stripe_records_sorted():
    records = generate_payment_records(n=30)
    timestamps = [r["timestamp"] for r in records]
    assert timestamps == sorted(timestamps)


def test_mongo_jobs_seed_referential_consistency():
    """Verify that generated job call_ids match booked Aria calls."""
    import sys
    sys.path.insert(0, ".")
    from scripts.generate_job_seed import generate_jobs

    calls = generate_call_records(n=200, seed=42)
    booked_ids = {c["call_id"] for c in calls if c["outcome"] == "booked"}
    jobs = generate_jobs()

    assert len(jobs) > 0
    assert len(jobs) == len(booked_ids)
    job_call_ids = {j["related_call_id"] for j in jobs}
    assert job_call_ids == booked_ids


def test_mongo_jobs_seed_statuses():
    """Verify all job statuses are valid."""
    import sys
    sys.path.insert(0, ".")
    from scripts.generate_job_seed import generate_jobs

    jobs = generate_jobs()
    valid = {"scheduled", "completed", "cancelled"}
    for j in jobs:
        assert j["status"] in valid


def test_mongo_jobs_seed_fields():
    """Verify job records have all required fields."""
    import sys
    sys.path.insert(0, ".")
    from scripts.generate_job_seed import generate_jobs

    jobs = generate_jobs()
    required = {"job_id", "related_call_id", "status", "service_category",
                "value", "technician", "scheduled_at"}
    for j in jobs:
        assert required.issubset(j.keys()), f"Missing fields: {required - j.keys()}"


# --- Windowed extraction: the backfill path -----------------------------

# One day inside the seeded 30-day span ending at REFERENCE_DATE (2026-07-16).
ONE_DAY = DateWindow.from_iso("2026-07-02", "2026-07-02")


def test_aria_windowed_extract_writes_only_that_day(tmp_path):
    cfg = LakeConfig(type="local", path=str(tmp_path))
    aria_calls.extract(cfg, window=ONE_DAY)
    records = read_raw(cfg, "aria_calls")
    assert records, "expected the seeded data to cover 2026-07-02"
    assert {r["timestamp"][:10] for r in records} == {"2026-07-02"}


def test_aria_backfilled_day_matches_the_full_refresh_of_that_day(tmp_path):
    """A refilled day must be indistinguishable from a full reload of it.

    This is the property that makes the backfill trustworthy: the seeded RNG
    stream is generated in full and only then filtered, so partitioning never
    shifts which records land on which day.
    """
    full = LakeConfig(type="local", path=str(tmp_path / "full"))
    windowed = LakeConfig(type="local", path=str(tmp_path / "windowed"))

    aria_calls.extract(full)
    aria_calls.extract(windowed, window=ONE_DAY)

    expected = [r for r in read_raw(full, "aria_calls") if r["timestamp"][:10] == "2026-07-02"]
    assert read_raw(windowed, "aria_calls") == expected


def test_stripe_backfilled_day_matches_the_full_refresh_of_that_day(tmp_path):
    full = LakeConfig(type="local", path=str(tmp_path / "full"))
    windowed = LakeConfig(type="local", path=str(tmp_path / "windowed"))

    stripe_payments.extract(full)
    stripe_payments.extract(windowed, window=ONE_DAY)

    expected = [
        r for r in read_raw(full, "stripe_payments") if r["timestamp"][:10] == "2026-07-02"
    ]
    assert read_raw(windowed, "stripe_payments") == expected


def test_mongo_window_filter_covers_the_whole_end_day():
    """ISO strings sort in calendar order, so the bound is the next bare date."""
    f = mongo_jobs._window_filter(DateWindow.from_iso("2026-07-01", "2026-07-07"))
    bounds = f["scheduled_at"]
    assert bounds["$gte"] == "2026-07-01"
    assert bounds["$lt"] == "2026-07-08"
    assert bounds["$gte"] <= "2026-07-01T00:00:00" < bounds["$lt"]
    assert "2026-07-07T23:59:59" < bounds["$lt"]
    assert not "2026-07-08T00:00:00" < bounds["$lt"]
