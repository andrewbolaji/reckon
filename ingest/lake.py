"""Data-lake writer. Abstracts local filesystem vs S3."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from ingest.config import LakeConfig


def _s3_client(config: LakeConfig):
    import boto3
    return boto3.client("s3", region_name=config.region)


def write_raw(config: LakeConfig, source: str, records: list[dict]) -> str:
    """Write a batch of raw JSON records to the lake, partitioned by date.

    Clears prior extracts for this source so re-runs are idempotent.
    """
    ts = datetime.now(tz=None)
    partition = ts.strftime("%Y/%m/%d")
    filename = f"{source}_{ts.strftime('%H%M%S')}.json"

    payload = json.dumps(records, default=str)

    if config.type == "s3":
        key = f"raw/{source}/{partition}/{filename}"
        _s3_client(config).put_object(
            Bucket=config.bucket, Key=key, Body=payload
        )
        return f"s3://{config.bucket}/{key}"

    # Local filesystem: clear prior extracts for idempotent loads
    source_root = Path(config.path) / "raw" / source
    if source_root.exists():
        shutil.rmtree(source_root)

    dest = source_root / partition
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / filename
    out.write_text(payload)
    return str(out)


def read_raw(config: LakeConfig, source: str) -> list[dict]:
    """Read the current raw extract for a source back from the lake.

    Mirrors ``write_raw`` for both backends:

    - **s3**: ``write_raw`` appends a new date-partitioned object each run and
      never deletes, so the newest key under ``raw/{source}/`` is the current
      run's extract. Keys are shaped ``raw/{source}/YYYY/MM/DD/{source}_HHMMSS.json``
      and therefore sort chronologically, so the max key is the latest. Reading
      only that object mirrors the local writer's ``rmtree`` idempotency and
      avoids re-loading stale extracts from earlier runs.
    - **local**: the writer clears prior extracts, so every JSON file under
      ``raw/{source}/`` belongs to the current run; read them all.
    """
    if config.type == "s3":
        client = _s3_client(config)
        prefix = f"raw/{source}/"
        keys = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=config.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        if not keys:
            return []
        latest = max(keys)
        body = client.get_object(Bucket=config.bucket, Key=latest)["Body"].read()
        return json.loads(body)

    source_dir = Path(config.path) / "raw" / source
    records: list[dict] = []
    for f in sorted(source_dir.rglob("*.json")):
        records.extend(json.loads(f.read_text()))
    return records
