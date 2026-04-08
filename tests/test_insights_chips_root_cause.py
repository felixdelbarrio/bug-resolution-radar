from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.insights.chips import issue_cards_html_from_df


def test_issue_cards_include_root_cause_chip_when_enabled() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-1",
                "summary": "No se visualiza el dashboard del cliente",
                "assignee": "QA",
                "__age_days": 12,
            }
        ]
    )
    html_out = issue_cards_html_from_df(
        df,
        key_to_url={"MEXBMI1-1": "https://jira.example/MEXBMI1-1"},
        key_to_meta={"MEXBMI1-1": ("New", "High", "")},
        include_root_cause=True,
    )
    assert "Causa raíz: Visualización / UI" in html_out


def test_issue_cards_do_not_include_root_cause_chip_by_default() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-2",
                "summary": "No se visualiza el dashboard del cliente",
                "assignee": "QA",
            }
        ]
    )
    html_out = issue_cards_html_from_df(
        df,
        key_to_url={},
        key_to_meta={"MEXBMI1-2": ("New", "High", "")},
    )
    assert "Causa raíz:" not in html_out
