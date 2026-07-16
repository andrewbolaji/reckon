"""Extractor for Aria AI voice-agent call records.

In production this would hit Aria's API; here it generates realistic sample data
so the pipeline is demonstrable end to end.
"""

import random
import uuid
from datetime import datetime, timedelta

from ingest.config import LakeConfig
from ingest.lake import write_raw

CALLERS = [
    "Maria Lopez", "James Chen", "Aisha Patel", "David Kim", "Sarah Johnson",
    "Omar Hassan", "Lisa Park", "Michael Brown", "Nina Kowalski", "Carlos Ruiz",
    "Emma Thompson", "Raj Gupta", "Fatima Ali", "Tom O'Brien", "Yuki Tanaka",
]

URGENCY_WEIGHTS = {"low": 0.30, "medium": 0.45, "high": 0.20, "critical": 0.05}
OUTCOME_WEIGHTS = {"booked": 0.42, "qualified": 0.18, "escalated": 0.15, "missed": 0.10, "resolved": 0.15}
TOPICS = [
    "plumbing repair", "HVAC maintenance", "electrical inspection",
    "roof leak", "water heater replacement", "drain cleaning",
    "emergency gas leak", "thermostat installation", "panel upgrade",
    "bathroom remodel estimate",
]


SEED = 42  # fixed seed for deterministic call_ids across runs


def generate_call_records(n: int = 200, days_back: int = 30, seed: int = SEED) -> list[dict]:
    """Generate n realistic Aria call records spread over days_back days."""
    rng = random.Random(seed)
    now = datetime.now(tz=None)  # naive UTC for sample data
    records = []
    for _ in range(n):
        ts = now - timedelta(
            days=rng.randint(0, days_back),
            hours=rng.randint(8, 18),
            minutes=rng.randint(0, 59),
        )
        urgency = rng.choices(
            list(URGENCY_WEIGHTS.keys()), list(URGENCY_WEIGHTS.values())
        )[0]
        outcome = rng.choices(
            list(OUTCOME_WEIGHTS.keys()), list(OUTCOME_WEIGHTS.values())
        )[0]
        duration = max(15, int(rng.gauss(180, 90)))

        records.append({
            "call_id": str(uuid.UUID(int=rng.getrandbits(128))),
            "timestamp": ts.isoformat(),
            "caller_name": rng.choice(CALLERS),
            "caller_phone": f"+1{rng.randint(2000000000, 9999999999)}",
            "urgency": urgency,
            "topic": rng.choice(TOPICS),
            "outcome": outcome,
            "duration_seconds": duration,
            "sentiment_score": round(rng.uniform(0.3, 1.0), 2),
            "agent_id": f"aria-{rng.randint(1, 3)}",
        })
    return sorted(records, key=lambda r: r["timestamp"])


def extract(lake_config: LakeConfig, num_records: int = 200) -> str:
    """Generate and land Aria call records in the data lake."""
    records = generate_call_records(num_records)
    path = write_raw(lake_config, "aria_calls", records)
    print(f"  Extracted {len(records)} Aria call records -> {path}")
    return path
