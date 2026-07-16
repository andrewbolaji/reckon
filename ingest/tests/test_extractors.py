"""Unit tests for the extractors."""

from ingest.extractors.aria_calls import generate_call_records
from ingest.extractors.stripe_payments import generate_payment_records


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
