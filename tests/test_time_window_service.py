from __future__ import annotations

import os
import time

import pandas as pd

from bug_resolution_radar.analytics.time_windows import TimeWindowService


def test_time_window_service_first_half_uses_complete_deterministic_ranges() -> None:
    service = TimeWindowService(timezone_name="UTC")

    window = service.current_window(pd.Timestamp("2026-03-12T08:00:00+00:00"))

    assert window.current_start == pd.Timestamp("2026-03-01")
    assert window.current_end == pd.Timestamp("2026-03-15")
    assert window.previous_start == pd.Timestamp("2026-02-15")
    assert window.previous_end == pd.Timestamp("2026-02-28")
    assert service.format_current_created_label(window, singular=False) == (
        "CREADAS DEL 01 AL 15 MAR"
    )
    assert service.format_previous_range_label(window) == "15 FEB - 28 FEB"


def test_time_window_service_second_half_handles_30_and_31_day_months() -> None:
    service = TimeWindowService(timezone_name="UTC")

    april = service.current_window("2026-04-30T23:00:00+00:00")
    may = service.current_window("2026-05-20T12:00:00+00:00")

    assert april.current_start == pd.Timestamp("2026-04-16")
    assert april.current_end == pd.Timestamp("2026-04-30")
    assert april.previous_start == pd.Timestamp("2026-04-01")
    assert april.previous_end == pd.Timestamp("2026-04-15")
    assert may.current_start == pd.Timestamp("2026-05-16")
    assert may.current_end == pd.Timestamp("2026-05-31")


def test_time_window_service_handles_february_and_leap_years() -> None:
    service = TimeWindowService(timezone_name="UTC")

    non_leap = service.current_window("2026-03-12T00:00:00+00:00")
    leap = service.current_window("2024-03-12T00:00:00+00:00")

    assert non_leap.previous_start == pd.Timestamp("2026-02-15")
    assert non_leap.previous_end == pd.Timestamp("2026-02-28")
    assert leap.previous_start == pd.Timestamp("2024-02-15")
    assert leap.previous_end == pd.Timestamp("2024-02-29")


def test_time_window_service_explicit_timezone_is_independent_of_os_timezone(
    monkeypatch: object,
) -> None:
    previous_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        service = TimeWindowService(timezone_name="America/Mexico_City")
        window = service.current_window("2026-03-16T01:00:00+00:00")
    finally:
        if previous_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", previous_tz)
        if hasattr(time, "tzset"):
            time.tzset()

    assert window.current_start == pd.Timestamp("2026-03-01")
    assert window.current_end == pd.Timestamp("2026-03-15")


def test_time_window_service_last_finished_mode_remains_complete() -> None:
    service = TimeWindowService(timezone_name="UTC")

    window = service.current_window(
        "2026-03-26T00:00:00+00:00",
        last_finished_only=True,
    )

    assert window.current_start == pd.Timestamp("2026-03-01")
    assert window.current_end == pd.Timestamp("2026-03-15")
    assert window.previous_start == pd.Timestamp("2026-02-15")
    assert window.previous_end == pd.Timestamp("2026-02-28")
