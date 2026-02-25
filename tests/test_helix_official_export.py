from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.exports.helix_official_export import _month_from_value


def test_month_from_value_returns_spanish_month_name() -> None:
    assert _month_from_value("2026-02-25T10:44:24+00:00") == "Febrero"
    assert _month_from_value(pd.Timestamp("2026-01-01T00:00:00Z")) == "Enero"
    assert _month_from_value("") == ""
