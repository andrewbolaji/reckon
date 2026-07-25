"""Data-lake writer. Abstracts local filesystem vs S3.

Two modes, and the difference matters:

- **Full refresh** (``window=None``): the historical behaviour. Every prior
  extract for the source is cleared and replaced, so a re-run is idempotent.
- **Windowed** (``window=DateWindow(...)``): only the days inside the window are
  cleared and rewritten, one file per day, so backfilling a missed week leaves
  every other day untouched. This is what makes a Dagster partition backfill a
  real refill rather than a full reload wearing a partition key.
"""

import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ingest.config import LakeConfig
from ingest.window import DateWindow, iso_date_of


def _s3_client(config: LakeConfig):
    import boto3
    return boto3.client("s3", region_name=config.region)


def _day_prefix(day) -> str:
    """Lake partition path for a day: ``YYYY/MM/DD``."""
    return day.strftime("%Y/%m/%d")


def _group_by_day(
    records: list[dict], date_field: str, window: DateWindow
) -> dict[str, list[dict]]:
    """Bucket records by calendar day, dropping anything outside the window.

    The drop is defensive: extractors already filter to the window, so an
    out-of-window record here would mean a caller bug. Silently writing it would
    land data in a partition the loader was never told to delete, which is the
    one way a windowed load can corrupt a day it does not own.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        day = iso_date_of(record.get(date_field))
        if day is not None and window.start_iso <= day <= window.end_iso:
            grouped[day].append(record)
    return grouped


def write_raw(
    config: LakeConfig,
    source: str,
    records: list[dict],
    window: DateWindow | None = None,
    date_field: str | None = None,
) -> str:
    """Write a batch of raw JSON records to the lake, partitioned by date.

    With no window, clears prior extracts for this source so re-runs are
    idempotent. With a window, ``date_field`` names the record field holding the
    event timestamp, and only that window's day partitions are replaced.
    """
    if window is not None:
        if not date_field:
            raise ValueError("date_field is required when writing a window")
        return _write_windowed(config, source, records, window, date_field)

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


def _write_windowed(
    config: LakeConfig,
    source: str,
    records: list[dict],
    window: DateWindow,
    date_field: str,
) -> str:
    """Replace exactly the window's day partitions, one file per day.

    Every day in the window is cleared first, including days that ended up with
    no records: a refill that finds a source empty for a day must leave that day
    empty, not leave yesterday's rows standing.
    """
    grouped = _group_by_day(records, date_field, window)

    if config.type == "s3":
        client = _s3_client(config)
        for day in window.days():
            prefix = f"raw/{source}/{_day_prefix(day)}/"
            _s3_delete_prefix(client, config.bucket, prefix)
        for day_iso, day_records in sorted(grouped.items()):
            key = f"raw/{source}/{day_iso.replace('-', '/')}/{source}_{day_iso}.json"
            client.put_object(
                Bucket=config.bucket,
                Key=key,
                Body=json.dumps(day_records, default=str),
            )
        return f"s3://{config.bucket}/raw/{source}/ [{window}]"

    source_root = Path(config.path) / "raw" / source
    for day in window.days():
        day_dir = source_root / _day_prefix(day)
        if day_dir.exists():
            shutil.rmtree(day_dir)
    for day_iso, day_records in sorted(grouped.items()):
        day_dir = source_root / day_iso.replace("-", "/")
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / f"{source}_{day_iso}.json").write_text(
            json.dumps(day_records, default=str)
        )
    return f"{source_root} [{window}]"


def _s3_delete_prefix(client, bucket: str, prefix: str) -> None:
    paginator = client.get_paginator("list_objects_v2")
    keys = [
        {"Key": obj["Key"]}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for obj in page.get("Contents", [])
    ]
    for i in range(0, len(keys), 1000):  # delete_objects caps at 1000 per call
        client.delete_objects(Bucket=bucket, Delete={"Objects": keys[i:i + 1000]})


def read_raw(
    config: LakeConfig, source: str, window: DateWindow | None = None
) -> list[dict]:
    """Read the current raw extract for a source back from the lake.

    Mirrors ``write_raw`` for both backends:

    - **s3**: an unwindowed ``write_raw`` appends a new date-partitioned object
      each run and never deletes, so the newest key under ``raw/{source}/`` is
      the current run's extract. Keys are shaped
      ``raw/{source}/YYYY/MM/DD/{source}_HHMMSS.json`` and therefore sort
      chronologically, so the max key is the latest. Reading only that object
      mirrors the local writer's ``rmtree`` idempotency and avoids re-loading
      stale extracts from earlier runs.
    - **local**: the writer clears prior extracts, so every JSON file under
      ``raw/{source}/`` belongs to the current run; read them all.

    With a window, both backends instead read every object under just that
    window's day partitions, which is what ``_write_windowed`` wrote.
    """
    if window is not None:
        return _read_windowed(config, source, window)

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


def _read_windowed(
    config: LakeConfig, source: str, window: DateWindow
) -> list[dict]:
    records: list[dict] = []

    if config.type == "s3":
        client = _s3_client(config)
        paginator = client.get_paginator("list_objects_v2")
        for day in window.days():
            prefix = f"raw/{source}/{_day_prefix(day)}/"
            for page in paginator.paginate(Bucket=config.bucket, Prefix=prefix):
                for obj in sorted(page.get("Contents", []), key=lambda o: o["Key"]):
                    body = client.get_object(
                        Bucket=config.bucket, Key=obj["Key"]
                    )["Body"].read()
                    records.extend(json.loads(body))
        return records

    source_root = Path(config.path) / "raw" / source
    for day in window.days():
        day_dir = source_root / _day_prefix(day)
        if not day_dir.exists():
            continue
        for f in sorted(day_dir.glob("*.json")):
            records.extend(json.loads(f.read_text()))
    return records
