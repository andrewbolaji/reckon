"""Inclusive date windows, the unit of partitioning for ingest.

A window is how a partitioned run says "refill exactly these days". Every
window-aware function in ``ingest`` takes one, and passing ``None`` instead
means the historical full-refresh behaviour (extract everything, truncate,
reload), so the non-partitioned path is unchanged.

Dates come off records as ISO-8601 strings (``2026-07-16T09:31:00``). The
warehouse stores every raw column as text, so the first 10 characters are the
calendar date in every backend. That prefix, not a cast, is what the loader and
the lake both key on.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

ISO_DATE_LEN = 10


def iso_date_of(value) -> str | None:
    """Return the ``YYYY-MM-DD`` prefix of a record timestamp.

    Accepts ISO strings, ``date``/``datetime`` objects (pymongo can return
    either depending on how the document was written), and returns None for
    anything empty or too short to carry a date.
    """
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:ISO_DATE_LEN]
    text = str(value)
    return text[:ISO_DATE_LEN] if len(text) >= ISO_DATE_LEN else None


@dataclass(frozen=True)
class DateWindow:
    """A closed interval of calendar days: both ``start`` and ``end`` included."""

    start: date
    end: date

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError(f"window end {self.end} precedes start {self.start}")

    @classmethod
    def from_iso(cls, start: str, end: str) -> "DateWindow":
        """Build from two ``YYYY-MM-DD`` strings (or full ISO timestamps)."""
        return cls(
            date.fromisoformat(start[:ISO_DATE_LEN]),
            date.fromisoformat(end[:ISO_DATE_LEN]),
        )

    @classmethod
    def from_time_window(cls, start: datetime, end: datetime) -> "DateWindow":
        """Build from Dagster's half-open ``[start, end)`` partition time window.

        Dagster's end is exclusive (a single 2026-07-16 daily partition spans
        2026-07-16T00:00 to 2026-07-17T00:00), so the last included day is the
        one before ``end``. A zero-length window would be nonsense, so a window
        that collapses is clamped to the single start day.
        """
        last = (end - timedelta(days=1)).date()
        return cls(start.date(), max(last, start.date()))

    def days(self) -> list[date]:
        """Every day in the window, ascending."""
        span = (self.end - self.start).days
        return [self.start + timedelta(days=i) for i in range(span + 1)]

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()

    def contains(self, value) -> bool:
        """True if a record timestamp falls on a day inside the window."""
        day = iso_date_of(value)
        return day is not None and self.start_iso <= day <= self.end_iso

    def __str__(self) -> str:
        return f"{self.start_iso}..{self.end_iso}"
