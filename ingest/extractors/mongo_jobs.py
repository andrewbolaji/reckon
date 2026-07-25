"""Extractor for MongoDB job records.

Reads from the reckon.jobs collection via pymongo and lands raw records
in the data lake, same extract-to-lake pattern as the other sources.
"""

from datetime import timedelta

from ingest.config import LakeConfig, MongoConfig
from ingest.lake import write_raw
from ingest.window import DateWindow


def _window_filter(window: DateWindow) -> dict:
    """Mongo query predicate for a date window.

    ``scheduled_at`` is stored as an ISO-8601 string (see
    ``mongo/init/seed_jobs.json``), and ISO strings sort lexicographically in
    calendar order, so a plain string range is a correct date range and can use
    an index. The window is inclusive of its end day, so the upper bound is the
    bare date of the following day: every timestamp on the end day sorts below
    it, because "2026-07-07T23:59:59" < "2026-07-08".
    """
    day_after_end = (window.end + timedelta(days=1)).isoformat()
    return {"scheduled_at": {"$gte": window.start_iso, "$lt": day_after_end}}


def extract(
    lake_config: LakeConfig,
    mongo_config: MongoConfig,
    window: DateWindow | None = None,
) -> str:
    """Read jobs from MongoDB and write to the data lake.

    With a window, the date predicate is pushed down to Mongo rather than
    filtered in Python, so a backfill reads only the days it is refilling.
    """
    from pymongo import MongoClient

    client = MongoClient(mongo_config.uri)
    db = client[mongo_config.database]
    query = _window_filter(window) if window is not None else {}
    cursor = db.jobs.find(query, {"_id": 0})
    records = list(cursor)
    client.close()

    if not records and window is None:
        print("  No job records found in MongoDB, skipping.")
        return ""

    path = write_raw(
        lake_config, "mongo_jobs", records, window=window, date_field="scheduled_at"
    )
    scope = f" for {window}" if window else ""
    print(f"  Extracted {len(records)} job records from MongoDB{scope} -> {path}")
    return path
