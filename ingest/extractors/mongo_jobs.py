"""Extractor for MongoDB job records.

Reads from the reckon.jobs collection via pymongo and lands raw records
in the data lake, same extract-to-lake pattern as the other sources.
"""

from ingest.config import LakeConfig, MongoConfig
from ingest.lake import write_raw


def extract(lake_config: LakeConfig, mongo_config: MongoConfig) -> str:
    """Read all jobs from MongoDB and write to the data lake."""
    from pymongo import MongoClient

    client = MongoClient(mongo_config.uri)
    db = client[mongo_config.database]
    cursor = db.jobs.find({}, {"_id": 0})
    records = list(cursor)
    client.close()

    if not records:
        print("  No job records found in MongoDB, skipping.")
        return ""

    path = write_raw(lake_config, "mongo_jobs", records)
    print(f"  Extracted {len(records)} job records from MongoDB -> {path}")
    return path
