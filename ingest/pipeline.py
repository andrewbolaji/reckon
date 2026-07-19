"""Main pipeline entrypoint. Runs extraction and loading."""

import time

from ingest.config import LakeConfig, MongoConfig, WarehouseConfig
from ingest.extractors import aria_calls, stripe_payments, mongo_jobs
from ingest.loader import load_to_warehouse

CALL_COLUMNS = [
    "call_id", "timestamp", "caller_name", "caller_phone",
    "urgency", "topic", "outcome", "duration_seconds",
    "sentiment_score", "agent_id",
]

PAYMENT_COLUMNS = [
    "payment_id", "timestamp", "amount_cents", "currency",
    "status", "payment_method", "customer_email",
    "description", "metadata_source",
]

JOB_COLUMNS = [
    "job_id", "related_call_id", "status", "service_category",
    "value", "technician", "scheduled_at", "completed_at",
]


def run():
    """Execute the full ingestion pipeline.

    Returns a dict of row counts by source for telemetry.
    """
    start = time.time()
    lake = LakeConfig.from_env()
    wh = WarehouseConfig.from_env()
    mongo = MongoConfig.from_env()

    print("=== Reckon Ingestion Pipeline ===")

    print("\n[1/6] Extracting Aria call records...")
    aria_calls.extract(lake)

    print("[2/6] Extracting Stripe payment records...")
    stripe_payments.extract(lake)

    print("[3/6] Extracting MongoDB job records...")
    mongo_jobs.extract(lake, mongo)

    rows = {}
    print("\n[4/6] Loading call records into warehouse...")
    rows["aria_calls"] = load_to_warehouse(lake, wh, "aria_calls", "aria_calls", CALL_COLUMNS)

    print("[5/6] Loading payment records into warehouse...")
    rows["stripe_payments"] = load_to_warehouse(lake, wh, "stripe_payments", "stripe_payments", PAYMENT_COLUMNS)

    print("[6/6] Loading job records into warehouse...")
    rows["jobs"] = load_to_warehouse(lake, wh, "mongo_jobs", "jobs", JOB_COLUMNS)

    duration = time.time() - start
    print(f"\n=== Ingestion complete ({duration:.1f}s) ===")
    return {"rows": rows, "duration_seconds": duration}


if __name__ == "__main__":
    run()
