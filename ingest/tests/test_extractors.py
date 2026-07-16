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
