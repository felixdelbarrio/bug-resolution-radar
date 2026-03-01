from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.pages import config_page


def test_analysis_window_defaults_preserves_business_default_when_cache_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_page, "load_issues_df", lambda _path: pd.DataFrame())

    max_months, selected_months = config_page._analysis_window_defaults(Settings())

    assert max_months == 12
    assert selected_months == 12


def test_analysis_window_defaults_preserves_configured_months_when_greater_than_available(
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "created": (now - timedelta(days=45)).isoformat(),
                "country": "México",
                "source_id": "jira:mexico:core",
            }
        ]
    )
    monkeypatch.setattr(config_page, "load_issues_df", lambda _path: df)

    settings = Settings(ANALYSIS_LOOKBACK_MONTHS=12)
    max_months, selected_months = config_page._analysis_window_defaults(settings)

    assert max_months >= 12
    assert selected_months == 12


def test_analysis_window_defaults_migrates_legacy_non_positive_values(monkeypatch) -> None:
    monkeypatch.setattr(config_page, "load_issues_df", lambda _path: pd.DataFrame())

    settings = Settings(ANALYSIS_LOOKBACK_MONTHS=0)
    max_months, selected_months = config_page._analysis_window_defaults(settings)

    assert max_months == 12
    assert selected_months == 12
