"""Daily partitions for the ingest assets.

Partitions start at the beginning of the demo data, which is anchored to
``REFERENCE_DATE``, the same fixed date the extractors generate against
(``ingest/extractors/aria_calls.py``). Anchoring the start to the real clock
instead would leave the earliest days of the dataset unaddressable.

They end wherever the real clock is, because Dagster will not create a partition
for a day that has not finished yet, and that guardrail is correct. It has one
visible consequence worth stating: the MongoDB jobs source is partitioned on
``scheduled_at``, which looks forward, so jobs booked for next week are not
missing, they are not yet due. The schedule ingests them as those days arrive.
"""

import os
from datetime import datetime, timedelta

from dagster import DailyPartitionsDefinition

# Matches the extractors' anchor.
REFERENCE_DATE = datetime.fromisoformat(
    os.getenv("REFERENCE_DATE", "2026-07-16T12:00:00")
)

# The generators spread events over the 30 days before REFERENCE_DATE and then
# subtract an intraday offset, which can push the earliest record into a 31st
# day. Starting a day earlier is what keeps a full-window run loading every
# generated record rather than quietly dropping the first few.
DEMO_DAYS_BACK = 31

WINDOW_START = (REFERENCE_DATE - timedelta(days=DEMO_DAYS_BACK)).date()

daily_partitions = DailyPartitionsDefinition(start_date=WINDOW_START.isoformat())


def full_window() -> tuple[str, str]:
    """The whole materialisable window as ``(start, end)`` partition keys.

    This is what ``make dagster-run`` and the compose one-shot fill, so one
    command loads the warehouse the way the old full-refresh script did. The end
    is the most recent complete day rather than a fixed date, because that is
    the furthest a partitioned pipeline can honestly have got to.
    """
    last = daily_partitions.get_last_partition_key()
    return WINDOW_START.isoformat(), last or WINDOW_START.isoformat()
