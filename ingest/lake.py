"""Data-lake writer — abstracts local filesystem vs S3."""

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

    # Local filesystem — clear prior extracts for idempotent loads
    source_root = Path(config.path) / "raw" / source
    if source_root.exists():
        shutil.rmtree(source_root)

    dest = source_root / partition
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / filename
    out.write_text(payload)
    return str(out)
