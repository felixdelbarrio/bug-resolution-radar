from __future__ import annotations

import os
import time
from datetime import date

import pandas as pd

from bug_resolution_radar.analytics.time_windows import ReportingWindow, TimeWindowService


def test_time_window_service_current_partial_window_when_last_completed_disabled() -> None:
    service = TimeWindowService(timezone_name="UTC")

    window = service.current_window(
        pd.Timestamp("2026-03-12T08:00:00+00:00"),
        last_finished_only=False,
    )

    assert isinstance(window, ReportingWindow)
    assert window.reference_date == date(2026, 3, 12)
    assert window.current_start == date(2026, 3, 1)
    assert window.current_end == date(2026, 3, 12)
    assert window.previous_start == date(2026, 2, 15)
    assert window.previous_end == date(2026, 2, 28)
    assert window.use_last_completed_fortnight is False
    assert service.format_current_created_label(window, singular=False) == (
        "CREADAS DEL 01 AL 12 MAR"
    )
    assert service.format_current_closed_label(window, singular=False) == ("CERRADAS DEL 01-12 MAR")
    assert service.format_previous_range_label(window) == "15-28 FEB"


def test_time_window_service_uses_last_completed_fortnight_when_enabled() -> None:
    service = TimeWindowService(timezone_name="UTC")

    window = service.current_window(
        "2026-03-12T00:00:00+00:00",
        last_finished_only=True,
    )

    assert window.current_start == date(2026, 2, 15)
    assert window.current_end == date(2026, 2, 28)
    assert window.previous_start == date(2026, 2, 1)
    assert window.previous_end == date(2026, 2, 14)
    assert window.use_last_completed_fortnight is True


def test_time_window_service_handles_february_and_leap_years() -> None:
    service = TimeWindowService(timezone_name="UTC")

    non_leap = service.current_window("2026-03-12T00:00:00+00:00")
    leap = service.current_window("2024-03-12T00:00:00+00:00")

    assert non_leap.previous_start == date(2026, 2, 15)
    assert non_leap.previous_end == date(2026, 2, 28)
    assert leap.previous_start == date(2024, 2, 15)
    assert leap.previous_end == date(2024, 2, 29)


def test_time_window_service_handles_30_and_31_day_months() -> None:
    service = TimeWindowService(timezone_name="UTC")

    april = service.current_window("2026-04-30T23:00:00+00:00")
    may = service.current_window("2026-05-20T12:00:00+00:00")

    assert april.current_start == date(2026, 4, 15)
    assert april.current_end == date(2026, 4, 30)
    assert april.previous_start == date(2026, 4, 1)
    assert april.previous_end == date(2026, 4, 14)
    assert may.current_start == date(2026, 5, 15)
    assert may.current_end == date(2026, 5, 20)


def test_time_window_service_handles_boundary_days() -> None:
    service = TimeWindowService(timezone_name="UTC")

    day_1 = service.current_window("2026-05-01T12:00:00+00:00")
    day_15 = service.current_window("2026-05-15T12:00:00+00:00")
    day_16 = service.current_window("2026-05-16T12:00:00+00:00")

    assert (day_1.current_start, day_1.current_end) == (
        date(2026, 5, 1),
        date(2026, 5, 1),
    )
    assert (day_1.previous_start, day_1.previous_end) == (
        date(2026, 4, 15),
        date(2026, 4, 30),
    )
    assert (day_15.current_start, day_15.current_end) == (
        date(2026, 5, 15),
        date(2026, 5, 15),
    )
    assert (day_15.previous_start, day_15.previous_end) == (
        date(2026, 5, 1),
        date(2026, 5, 14),
    )
    assert (day_16.current_start, day_16.current_end) == (
        date(2026, 5, 15),
        date(2026, 5, 16),
    )


def test_time_window_service_explicit_timezone_is_independent_of_os_timezone(
    monkeypatch: object,
) -> None:
    previous_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        service = TimeWindowService(timezone_name="America/Mexico_City")
        window = service.current_window("2026-03-12T08:00:00+00:00")
    finally:
        if previous_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", previous_tz)
        if hasattr(time, "tzset"):
            time.tzset()

    assert window.current_start == date(2026, 3, 1)
    assert window.current_end == date(2026, 3, 12)


def test_time_window_service_formats_compact_ranges() -> None:
    service = TimeWindowService(timezone_name="UTC")

    assert service.format_compact_range(date(2026, 4, 1), date(2026, 4, 15)) == "01-15 ABR"
    assert service.format_compact_range(date(2026, 4, 16), date(2026, 4, 30)) == "16-30 ABR"
    assert service.format_compact_range(date(2026, 2, 15), date(2026, 3, 1)) == ("15 FEB-01 MAR")
