"""Round-trip tests for the data-lake read/write path (local + S3)."""

import json

import boto3
import pytest
from moto import mock_aws

from ingest.config import LakeConfig
from ingest.lake import read_raw, write_raw
from ingest.window import DateWindow

RECORDS = [
    {"id": "a1", "amount": 10, "note": "first"},
    {"id": "b2", "amount": 20, "note": "second"},
]

BUCKET = "reckon-test-lake"

# Three days of records, one per day, for the windowed tests.
DAY1 = {"id": "d1", "ts": "2026-07-01T09:00:00"}
DAY2 = {"id": "d2", "ts": "2026-07-02T09:00:00"}
DAY3 = {"id": "d3", "ts": "2026-07-03T09:00:00"}
SPREAD = [DAY1, DAY2, DAY3]
WHOLE = DateWindow.from_iso("2026-07-01", "2026-07-03")


def test_local_round_trip(tmp_path):
    cfg = LakeConfig(type="local", path=str(tmp_path))
    write_raw(cfg, "widgets", RECORDS)
    assert read_raw(cfg, "widgets") == RECORDS


def test_local_missing_source_returns_empty(tmp_path):
    cfg = LakeConfig(type="local", path=str(tmp_path))
    assert read_raw(cfg, "never_written") == []


@mock_aws
def test_s3_round_trip():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
    cfg = LakeConfig(type="s3", bucket=BUCKET, region="us-east-1")
    write_raw(cfg, "widgets", RECORDS)
    assert read_raw(cfg, "widgets") == RECORDS


@mock_aws
def test_s3_empty_source_returns_empty():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
    cfg = LakeConfig(type="s3", bucket=BUCKET, region="us-east-1")
    assert read_raw(cfg, "widgets") == []


@mock_aws
def test_s3_reads_latest_object_only():
    """S3 keeps prior extracts; read_raw must return only the newest run's data."""
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=BUCKET)
    cfg = LakeConfig(type="s3", bucket=BUCKET, region="us-east-1")
    # Keys sort chronologically: raw/{source}/YYYY/MM/DD/{source}_HHMMSS.json
    client.put_object(
        Bucket=BUCKET,
        Key="raw/widgets/2026/07/24/widgets_120000.json",
        Body=json.dumps([{"id": "stale"}]),
    )
    client.put_object(
        Bucket=BUCKET,
        Key="raw/widgets/2026/07/24/widgets_130000.json",
        Body=json.dumps([{"id": "fresh"}]),
    )
    assert read_raw(cfg, "widgets") == [{"id": "fresh"}]


# --- Windowed writes: the backfill path ---------------------------------


def _ids(records):
    return sorted(r["id"] for r in records)


def test_windowed_round_trip_local(tmp_path):
    cfg = LakeConfig(type="local", path=str(tmp_path))
    write_raw(cfg, "widgets", SPREAD, window=WHOLE, date_field="ts")
    assert _ids(read_raw(cfg, "widgets", window=WHOLE)) == ["d1", "d2", "d3"]


def test_windowed_read_returns_only_the_requested_days(tmp_path):
    cfg = LakeConfig(type="local", path=str(tmp_path))
    write_raw(cfg, "widgets", SPREAD, window=WHOLE, date_field="ts")
    just_day2 = DateWindow.from_iso("2026-07-02", "2026-07-02")
    assert _ids(read_raw(cfg, "widgets", window=just_day2)) == ["d2"]


def test_refilling_one_day_leaves_the_others_alone(tmp_path):
    """The property that makes a backfill a backfill and not a full reload."""
    cfg = LakeConfig(type="local", path=str(tmp_path))
    write_raw(cfg, "widgets", SPREAD, window=WHOLE, date_field="ts")

    just_day2 = DateWindow.from_iso("2026-07-02", "2026-07-02")
    replacement = [{"id": "d2-new", "ts": "2026-07-02T11:00:00"}]
    write_raw(cfg, "widgets", replacement, window=just_day2, date_field="ts")

    assert _ids(read_raw(cfg, "widgets", window=WHOLE)) == ["d1", "d2-new", "d3"]


def test_refilling_a_day_that_is_now_empty_clears_it(tmp_path):
    """A source that returns nothing for a day must empty that day, not keep it."""
    cfg = LakeConfig(type="local", path=str(tmp_path))
    write_raw(cfg, "widgets", SPREAD, window=WHOLE, date_field="ts")

    just_day2 = DateWindow.from_iso("2026-07-02", "2026-07-02")
    write_raw(cfg, "widgets", [], window=just_day2, date_field="ts")

    assert _ids(read_raw(cfg, "widgets", window=WHOLE)) == ["d1", "d3"]


def test_windowed_write_drops_out_of_window_records(tmp_path):
    """Out-of-window records would land in a day the loader never deletes."""
    cfg = LakeConfig(type="local", path=str(tmp_path))
    just_day2 = DateWindow.from_iso("2026-07-02", "2026-07-02")
    write_raw(cfg, "widgets", SPREAD, window=just_day2, date_field="ts")
    assert _ids(read_raw(cfg, "widgets")) == ["d2"]


def test_windowed_write_requires_a_date_field(tmp_path):
    cfg = LakeConfig(type="local", path=str(tmp_path))
    with pytest.raises(ValueError, match="date_field"):
        write_raw(cfg, "widgets", SPREAD, window=WHOLE)


def test_windowed_read_of_never_written_source_is_empty(tmp_path):
    cfg = LakeConfig(type="local", path=str(tmp_path))
    assert read_raw(cfg, "never_written", window=WHOLE) == []


def test_full_refresh_still_clears_windowed_partitions(tmp_path):
    """window=None keeps its old contract: wipe the source, write one file."""
    cfg = LakeConfig(type="local", path=str(tmp_path))
    write_raw(cfg, "widgets", SPREAD, window=WHOLE, date_field="ts")
    write_raw(cfg, "widgets", RECORDS)
    assert read_raw(cfg, "widgets") == RECORDS


@mock_aws
def test_windowed_round_trip_s3():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
    cfg = LakeConfig(type="s3", bucket=BUCKET, region="us-east-1")
    write_raw(cfg, "widgets", SPREAD, window=WHOLE, date_field="ts")
    assert _ids(read_raw(cfg, "widgets", window=WHOLE)) == ["d1", "d2", "d3"]


@mock_aws
def test_refilling_one_day_leaves_the_others_alone_s3():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
    cfg = LakeConfig(type="s3", bucket=BUCKET, region="us-east-1")
    write_raw(cfg, "widgets", SPREAD, window=WHOLE, date_field="ts")

    just_day2 = DateWindow.from_iso("2026-07-02", "2026-07-02")
    replacement = [{"id": "d2-new", "ts": "2026-07-02T11:00:00"}]
    write_raw(cfg, "widgets", replacement, window=just_day2, date_field="ts")

    assert _ids(read_raw(cfg, "widgets", window=WHOLE)) == ["d1", "d2-new", "d3"]
