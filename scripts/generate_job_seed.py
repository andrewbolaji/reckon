"""Generate seed data for the MongoDB jobs collection.

Produces mongo/init/seed_jobs.json by running the Aria call generator with
the same fixed seed, picking out booked calls, and creating one job per
booked call. This keeps Mongo as a genuine source while guaranteeing
referential consistency with Aria call_ids.

Run: python -m scripts.generate_job_seed
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Import the Aria generator to get deterministic call records
from ingest.extractors.aria_calls import generate_call_records, REFERENCE_DATE, TOPICS

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
}

TECHNICIANS = [
    "Mike Rivera", "Sandra Liu", "Tyler Brooks", "Priya Sharma",
    "Jake Morrison", "Ana Gutierrez", "Chris Wallace", "Kenji Ota",
]

STATUS_WEIGHTS = {"completed": 0.70, "scheduled": 0.20, "cancelled": 0.10}


def generate_jobs() -> list[dict]:
    """Create one job per booked Aria call using the same seed."""
    calls = generate_call_records(n=200, days_back=30, seed=42)
    booked = [c for c in calls if c["outcome"] == "booked"]

    rng = random.Random(99)  # separate seed for job-specific fields
    jobs = []

    for call in booked:
        call_ts = datetime.fromisoformat(call["timestamp"])
        status = rng.choices(
            list(STATUS_WEIGHTS.keys()), list(STATUS_WEIGHTS.values())
        )[0]

        topic = call["topic"]
        price_range = SERVICES.get(topic, (150, 500))
        value = round(rng.uniform(price_range[0], price_range[1]), 2)

        scheduled_at = call_ts + timedelta(
            days=rng.randint(1, 5),
            hours=rng.randint(0, 8),
        )
        completed_at = None
        if status == "completed":
            completed_at = (
                scheduled_at + timedelta(
                    hours=rng.randint(1, 6),
                    minutes=rng.randint(0, 59),
                )
            ).isoformat()
        elif status == "scheduled":
            # future scheduled jobs: push scheduled_at forward
            scheduled_at = REFERENCE_DATE + timedelta(days=rng.randint(1, 14))

        jobs.append({
            "job_id": str(uuid.UUID(int=rng.getrandbits(128))),
            "related_call_id": call["call_id"],
            "status": status,
            "service_category": topic,
            "value": value,
            "technician": rng.choice(TECHNICIANS),
            "scheduled_at": scheduled_at.isoformat(),
            "completed_at": completed_at,
        })

    return jobs


if __name__ == "__main__":
    jobs = generate_jobs()
    out = Path("mongo/init/seed_jobs.json")
    out.write_text(json.dumps(jobs, indent=2, default=str))
    print(f"Generated {len(jobs)} jobs -> {out}")

    # Stats
    by_status = {}
    for j in jobs:
        by_status[j["status"]] = by_status.get(j["status"], 0) + 1
    for s, c in sorted(by_status.items()):
        print(f"  {s}: {c}")
