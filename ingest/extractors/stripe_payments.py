"""Extractor for Stripe-style payment records.

In production this would use the Stripe API with cursor-based pagination;
here it generates realistic sample data tied to the Aria call outcomes.
"""

import random
import uuid
from datetime import datetime, timedelta

from ingest.config import LakeConfig
from ingest.lake import write_raw

SERVICES = {
    "plumbing repair": (150, 450),
    "HVAC maintenance": (200, 600),
    "electrical inspection": (100, 300),
    "roof leak": (300, 1200),
    "water heater replacement": (800, 2500),
    "drain cleaning": (100, 350),
    "emergency gas leak": (500, 2000),
    "thermostat installation": (150, 400),
    "panel upgrade": (600, 3000),
    "bathroom remodel estimate": (0, 0),  # estimate only, no charge
}

STATUSES = ["succeeded", "succeeded", "succeeded", "succeeded", "refunded", "failed"]
PAYMENT_METHODS = ["card", "card", "card", "ach", "card"]


def generate_payment_records(n: int = 150, days_back: int = 30) -> list[dict]:
    """Generate n realistic Stripe-like payment records."""
    now = datetime.now(tz=None)  # naive UTC for sample data
    records = []
    for _ in range(n):
        service = random.choice(list(SERVICES.keys()))
        lo, hi = SERVICES[service]
        if hi == 0:
            continue
        amount = random.randint(lo * 100, hi * 100)  # cents
        ts = now - timedelta(
            days=random.randint(0, days_back),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        records.append({
            "payment_id": f"pi_{uuid.uuid4().hex[:24]}",
            "timestamp": ts.isoformat(),
            "amount_cents": amount,
            "currency": "usd",
            "status": random.choice(STATUSES),
            "payment_method": random.choice(PAYMENT_METHODS),
            "customer_email": f"customer{random.randint(100,999)}@example.com",
            "description": service,
            "metadata_source": "aria_booking",
        })
    return sorted(records, key=lambda r: r["timestamp"])


def extract(lake_config: LakeConfig, num_records: int = 150) -> str:
    """Generate and land Stripe payment records in the data lake."""
    records = generate_payment_records(num_records)
    path = write_raw(lake_config, "stripe_payments", records)
    print(f"  Extracted {len(records)} Stripe payment records -> {path}")
    return path
