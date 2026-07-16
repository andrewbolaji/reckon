"""Main pipeline entrypoint — runs extraction and loading."""

from ingest.config import LakeConfig, WarehouseConfig
from ingest.extractors import aria_calls, stripe_payments
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


def run():
    """Execute the full ingestion pipeline."""
    lake = LakeConfig.from_env()
    wh = WarehouseConfig.from_env()

    print("=== Reckon Ingestion Pipeline ===")

    print("\n[1/4] Extracting Aria call records...")
    aria_calls.extract(lake)

    print("[2/4] Extracting Stripe payment records...")
    stripe_payments.extract(lake)

    print("\n[3/4] Loading call records into warehouse...")
    load_to_warehouse(lake, wh, "aria_calls", "aria_calls", CALL_COLUMNS)

    print("[4/4] Loading payment records into warehouse...")
    load_to_warehouse(lake, wh, "stripe_payments", "stripe_payments", PAYMENT_COLUMNS)

    print("\n=== Ingestion complete ===")


if __name__ == "__main__":
    run()
