from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.tabs.overview_tab import _exit_funnel_counts_from_filtered


def test_exit_funnel_counts_from_filtered_scope() -> None:
    dff = pd.DataFrame(
        {
            "status": [
                "Accepted",
                "Ready to Deploy",
                "Accepted",
                "Deployed",
                "Blocked",
                "Ready to Deploy",
            ]
        }
    )
    accepted, ready, total = _exit_funnel_counts_from_filtered(dff)
    assert accepted == 2
    assert ready == 2
    assert total == 4


def test_exit_funnel_counts_from_filtered_empty_or_missing_status() -> None:
    assert _exit_funnel_counts_from_filtered(pd.DataFrame()) == (0, 0, 0)
    assert _exit_funnel_counts_from_filtered(pd.DataFrame({"priority": ["High"]})) == (0, 0, 0)
