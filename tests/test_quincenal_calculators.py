from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.quincenal_calculators import (
    ClosedIncidentsCalculator,
    CreatedIncidentsCalculator,
    NormalizedIssueFrame,
    ResolutionMetricsCalculator,
    build_inclusion_debug_frame,
)
from bug_resolution_radar.analytics.time_windows import TimeWindowService


def test_quincenal_calculators_count_created_closed_and_total_deterministically() -> None:
    window = TimeWindowService().current_window("2026-03-12T00:00:00+00:00")
    frame = NormalizedIssueFrame.from_df(
        pd.DataFrame(
            [
                {
                    "key": "CUR-1",
                    "status": "New",
                    "created": "2026-03-01T10:00:00+00:00",
                    "updated": "2026-03-12T10:00:00+00:00",
                    "resolved": None,
                },
                {
                    "key": "CUR-2",
                    "status": "Resolved",
                    "created": "2026-03-12T23:00:00+00:00",
                    "updated": "2026-03-12T23:00:00+00:00",
                    "resolved": "2026-03-12T23:00:00+00:00",
                },
                {
                    "key": "PREV-1",
                    "status": "New",
                    "created": "2026-02-15T00:00:00+00:00",
                    "updated": "2026-03-12T10:00:00+00:00",
                    "resolved": None,
                },
                {
                    "key": "PREV-2",
                    "status": "Resolved",
                    "created": "2026-02-28T23:59:59+00:00",
                    "updated": "2026-03-10T10:00:00+00:00",
                    "resolved": "2026-03-10T10:00:00+00:00",
                },
                {
                    "key": "OLD",
                    "status": "New",
                    "created": "2026-02-14T23:59:59+00:00",
                    "updated": "2026-03-12T10:00:00+00:00",
                    "resolved": None,
                },
                {
                    "key": "FINAL-PROXY",
                    "status": "Accepted",
                    "created": "2026-03-11T10:00:00+00:00",
                    "updated": "2026-03-12T10:00:00+00:00",
                    "resolved": None,
                },
            ]
        )
    )

    created = CreatedIncidentsCalculator().calculate(frame, window=window)
    closed = ClosedIncidentsCalculator().calculate(frame, window=window)

    assert created.current == 3
    assert created.previous == 2
    assert created.total == 5
    assert closed.current == 3
    assert closed.previous == 0
    assert frame.df.loc[created.total_mask, "key"].tolist() == [
        "CUR-1",
        "CUR-2",
        "PREV-1",
        "PREV-2",
        "FINAL-PROXY",
    ]
    assert frame.df.loc[closed.current_mask, "key"].tolist() == [
        "CUR-2",
        "PREV-2",
        "FINAL-PROXY",
    ]


def test_resolution_metrics_use_only_valid_closed_current_rows() -> None:
    window = TimeWindowService().current_window("2026-03-12T00:00:00+00:00")
    frame = NormalizedIssueFrame.from_df(
        pd.DataFrame(
            [
                {
                    "key": "LONG",
                    "status": "Resolved",
                    "created": "2026-03-01T00:00:00+00:00",
                    "updated": "2026-03-10T00:00:00+00:00",
                    "resolved": "2026-03-10T00:00:00+00:00",
                },
                {
                    "key": "SHORT",
                    "status": "Accepted",
                    "created": "2026-03-11T00:00:00+00:00",
                    "updated": "2026-03-12T00:00:00+00:00",
                    "resolved": "2026-03-12T00:00:00+00:00",
                },
                {
                    "key": "OPEN",
                    "status": "New",
                    "created": "2026-03-01T00:00:00+00:00",
                    "updated": "2026-03-12T00:00:00+00:00",
                    "resolved": None,
                },
                {
                    "key": "CORRUPT",
                    "status": "Resolved",
                    "created": "2026-03-10T00:00:00+00:00",
                    "updated": "2026-03-05T00:00:00+00:00",
                    "resolved": "2026-03-05T00:00:00+00:00",
                },
                {
                    "key": "INVALID",
                    "status": "Resolved",
                    "created": "not a date",
                    "updated": "2026-03-12T00:00:00+00:00",
                    "resolved": "2026-03-12T00:00:00+00:00",
                },
                {
                    "key": "OUTSIDE",
                    "status": "Resolved",
                    "created": "2026-02-15T00:00:00+00:00",
                    "updated": "2026-02-28T00:00:00+00:00",
                    "resolved": "2026-02-28T00:00:00+00:00",
                },
            ]
        )
    )

    result = ResolutionMetricsCalculator().calculate(frame, window=window)

    assert result.current_mean == 5.0
    assert result.current_min == 1.0
    assert result.current_max == 9.0
    assert frame.df.loc[result.current_mask, "key"].tolist() == ["LONG", "SHORT"]
    assert result.current_days.min() >= 0


def test_resolution_metrics_min_comes_from_closed_population_not_default_zero() -> None:
    window = TimeWindowService().current_window("2026-03-12T00:00:00+00:00")
    frame = NormalizedIssueFrame.from_df(
        pd.DataFrame(
            [
                {
                    "key": "FIVE",
                    "status": "Resolved",
                    "created": "2026-03-05T00:00:00+00:00",
                    "resolved": "2026-03-10T00:00:00+00:00",
                },
                {
                    "key": "SEVEN",
                    "status": "Resolved",
                    "created": "2026-03-04T00:00:00+00:00",
                    "resolved": "2026-03-11T00:00:00+00:00",
                },
            ]
        )
    )

    result = ResolutionMetricsCalculator().calculate(frame, window=window)

    assert result.current_mean == 6.0
    assert result.current_min == 5.0
    assert result.current_max == 7.0


def test_inclusion_debug_frame_lists_created_and_real_closed_membership() -> None:
    window = TimeWindowService().current_window("2026-03-12T00:00:00+00:00")
    frame = NormalizedIssueFrame.from_df(
        pd.DataFrame(
            [
                {
                    "key": "A-1",
                    "created": "2026-03-05T00:00:00+00:00",
                    "resolved": None,
                },
                {
                    "key": "A-2",
                    "created": "2026-02-20T00:00:00+00:00",
                    "resolved": "2026-03-12T00:00:00+00:00",
                },
                {
                    "key": "A-3",
                    "created": "2026-03-10T00:00:00+00:00",
                    "updated": "2026-03-12T00:00:00+00:00",
                    "resolved": None,
                    "status": "Accepted",
                },
            ]
        )
    )

    debug = build_inclusion_debug_frame(frame, window=window)

    assert debug.to_dict("records") == [
        {
            "ID": "A-1",
            "created_date": "2026-03-05",
            "resolved_date": "",
            "included_in_created": True,
            "included_in_closed": False,
        },
        {
            "ID": "A-2",
            "created_date": "2026-02-20",
            "resolved_date": "2026-03-12",
            "included_in_created": False,
            "included_in_closed": True,
        },
        {
            "ID": "A-3",
            "created_date": "2026-03-10",
            "resolved_date": "",
            "included_in_created": True,
            "included_in_closed": True,
        },
    ]


def test_quincenal_calculators_handle_empty_and_corrupt_dates() -> None:
    window = TimeWindowService().current_window("2026-03-12T00:00:00+00:00")
    frame = NormalizedIssueFrame.from_df(pd.DataFrame([{"key": "BAD", "created": "bad"}]))

    created = CreatedIncidentsCalculator().calculate(frame, window=window)
    closed = ClosedIncidentsCalculator().calculate(frame, window=window)
    resolution = ResolutionMetricsCalculator().calculate(frame, window=window)
    empty_resolution = ResolutionMetricsCalculator().calculate(
        NormalizedIssueFrame.from_df(pd.DataFrame()),
        window=window,
    )

    assert created.current == 0
    assert created.previous == 0
    assert created.total == 0
    assert closed.current == 0
    assert resolution.current_mean is None
    assert empty_resolution.current_mean is None
