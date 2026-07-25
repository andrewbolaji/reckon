"""Tests for the date window, the unit of ingest partitioning."""

from datetime import date, datetime

import pytest

from ingest.window import DateWindow, iso_date_of


def test_days_are_inclusive_of_both_ends():
    w = DateWindow.from_iso("2026-07-01", "2026-07-03")
    assert w.days() == [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)]


def test_single_day_window_has_one_day():
    w = DateWindow.from_iso("2026-07-01", "2026-07-01")
    assert w.days() == [date(2026, 7, 1)]


def test_from_iso_accepts_full_timestamps():
    w = DateWindow.from_iso("2026-07-01T09:30:00", "2026-07-02T23:00:00")
    assert (w.start_iso, w.end_iso) == ("2026-07-01", "2026-07-02")


def test_backwards_window_is_rejected():
    with pytest.raises(ValueError, match="precedes start"):
        DateWindow(date(2026, 7, 5), date(2026, 7, 1))


def test_from_time_window_converts_dagsters_exclusive_end():
    # Dagster hands out [start, end) — a single 2026-07-16 daily partition runs
    # to 2026-07-17T00:00 — so the last included day is the one before end.
    w = DateWindow.from_time_window(
        datetime(2026, 7, 16), datetime(2026, 7, 17)
    )
    assert (w.start_iso, w.end_iso) == ("2026-07-16", "2026-07-16")


def test_from_time_window_over_a_range():
    w = DateWindow.from_time_window(
        datetime(2026, 6, 16), datetime(2026, 7, 17)
    )
    assert (w.start_iso, w.end_iso) == ("2026-06-16", "2026-07-16")


def test_from_time_window_never_collapses_below_a_day():
    # A degenerate [start, start) window would otherwise produce an end before
    # its start and raise. Clamp to the single start day instead.
    w = DateWindow.from_time_window(datetime(2026, 7, 16), datetime(2026, 7, 16))
    assert w.days() == [date(2026, 7, 16)]


def test_contains_matches_on_the_calendar_day_only():
    w = DateWindow.from_iso("2026-07-01", "2026-07-02")
    assert w.contains("2026-07-01T00:00:00")
    assert w.contains("2026-07-02T23:59:59")
    assert not w.contains("2026-06-30T23:59:59")
    assert not w.contains("2026-07-03T00:00:00")


def test_contains_rejects_unusable_timestamps():
    w = DateWindow.from_iso("2026-07-01", "2026-07-02")
    assert not w.contains(None)
    assert not w.contains("")
    assert not w.contains("2026-07")


def test_iso_date_of_handles_strings_and_datetimes():
    assert iso_date_of("2026-07-16T12:00:00") == "2026-07-16"
    assert iso_date_of(datetime(2026, 7, 16, 12)) == "2026-07-16"
    assert iso_date_of(date(2026, 7, 16)) == "2026-07-16"
    assert iso_date_of(None) is None
