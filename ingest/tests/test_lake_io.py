"""Round-trip tests for the data-lake read/write path (local + S3)."""

import json

import boto3
from moto import mock_aws

from ingest.config import LakeConfig
from ingest.lake import read_raw, write_raw

RECORDS = [
    {"id": "a1", "amount": 10, "note": "first"},
    {"id": "b2", "amount": 20, "note": "second"},
]

BUCKET = "reckon-test-lake"


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
