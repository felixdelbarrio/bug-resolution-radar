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


def test_issue_cards_infer_root_cause_from_full_summary_not_truncated_preview() -> None:
    long_prefix = "Detalle general del caso " * 18
    long_summary = (
        f"{long_prefix} - PAGOS / SENDA BNC / TRANSFERENCIAS EN TIEMPO REAL / "
        "NO ACREDITA EL MOVIMIENTO"
    )
    df = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-3",
                "summary": long_summary,
                "assignee": "QA",
                "__age_days": 3,
            }
        ]
    )
    html_out = issue_cards_html_from_df(
        df,
        key_to_url={"MEXBMI1-3": "https://jira.example/MEXBMI1-3"},
        key_to_meta={"MEXBMI1-3": ("New", "Medium", "")},
        include_root_cause=True,
        summary_max_chars=100,
    )
    assert "Causa raíz: Transferencias en tiempo real" in html_out


def test_issue_cards_use_description_to_infer_root_cause_when_summary_is_generic() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-4",
                "summary": "Incidencia operativa sin detalle",
                "description": "Timeout y error 504 al invocar endpoint backend",
                "assignee": "QA",
                "__age_days": 2,
            }
        ]
    )
    html_out = issue_cards_html_from_df(
        df,
        key_to_url={"MEXBMI1-4": "https://jira.example/MEXBMI1-4"},
        key_to_meta={"MEXBMI1-4": ("New", "Medium", "")},
        include_root_cause=True,
    )
    assert "Causa raíz: Conectividad / timeout" in html_out
