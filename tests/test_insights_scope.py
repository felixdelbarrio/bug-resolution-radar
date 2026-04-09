from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.insights_scope import (
    INSIGHTS_VIEW_MODE_ACCUMULATED,
    INSIGHTS_VIEW_MODE_QUINCENAL,
    build_insights_combo_context,
)


def test_insights_combo_context_default_status_excludes_core_final_states() -> None:
    df = pd.DataFrame(
        [
            {"key": "A-1", "status": "New", "priority": "High", "summary": "Error de pagos"},
            {
                "key": "A-2",
                "status": "Analysing",
                "priority": "Medium",
                "summary": "Error de pagos",
            },
            {"key": "A-3", "status": "Accepted", "priority": "Low", "summary": "Error de pagos"},
            {
                "key": "A-4",
                "status": "Ready to Deploy",
                "priority": "Low",
                "summary": "Error de pagos",
            },
            {"key": "A-5", "status": "Deployed", "priority": "Low", "summary": "Error de pagos"},
        ]
    )

    ctx = build_insights_combo_context(
        accumulated_df=df,
        quincenal_df=df,
        view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
        selected_statuses=[],
        selected_priorities=[],
        selected_functionalities=[],
        apply_default_status_when_empty=True,
    )

    assert list(ctx.selected_statuses) == ["New", "Analysing"]
    assert set(ctx.filtered_df["status"].tolist()) == {"New", "Analysing"}


def test_insights_combo_context_functionality_options_follow_selected_view() -> None:
    accumulated = pd.DataFrame(
        [
            {"key": "A-1", "status": "New", "priority": "High", "summary": "Error de pagos"},
            {"key": "A-2", "status": "New", "priority": "High", "summary": "Fallo de login"},
        ]
    )
    quincenal = pd.DataFrame(
        [
            {"key": "Q-1", "status": "New", "priority": "High", "summary": "Fallo de login"},
        ]
    )

    ctx_quincenal = build_insights_combo_context(
        accumulated_df=accumulated,
        quincenal_df=quincenal,
        view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
    )
    ctx_accumulated = build_insights_combo_context(
        accumulated_df=accumulated,
        quincenal_df=quincenal,
        view_mode=INSIGHTS_VIEW_MODE_ACCUMULATED,
    )

    assert list(ctx_quincenal.functionality_options) == ["Login y acceso"]
    assert set(ctx_accumulated.functionality_options) == {"Pagos", "Login y acceso"}


def test_insights_combo_context_applies_selected_functionalities() -> None:
    df = pd.DataFrame(
        [
            {"key": "A-1", "status": "New", "priority": "High", "summary": "Error de pagos"},
            {"key": "A-2", "status": "New", "priority": "High", "summary": "Fallo de login"},
        ]
    )

    ctx = build_insights_combo_context(
        accumulated_df=df,
        quincenal_df=df,
        view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
        selected_functionalities=["Pagos"],
    )

    assert "__insights_theme" in ctx.filtered_df.columns
    assert set(ctx.filtered_df["__insights_theme"].tolist()) == {"Pagos"}
    assert ctx.filtered_df["key"].tolist() == ["A-1"]


def test_insights_combo_context_default_status_uses_operational_order_and_excludes_discarded() -> (
    None
):
    df = pd.DataFrame(
        [
            {"key": "A-1", "status": "Discarded", "priority": "High", "summary": "x"},
            {"key": "A-2", "status": "Ready to Verify", "priority": "High", "summary": "x"},
            {"key": "A-3", "status": "Blocked", "priority": "High", "summary": "x"},
            {"key": "A-4", "status": "New", "priority": "High", "summary": "x"},
            {"key": "A-5", "status": "To Rework", "priority": "High", "summary": "x"},
            {"key": "A-6", "status": "In Progress", "priority": "High", "summary": "x"},
            {"key": "A-7", "status": "Test", "priority": "High", "summary": "x"},
            {"key": "A-8", "status": "Analysing", "priority": "High", "summary": "x"},
            {"key": "A-9", "status": "Accepted", "priority": "High", "summary": "x"},
        ]
    )

    ctx = build_insights_combo_context(
        accumulated_df=df,
        quincenal_df=df,
        view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
        selected_statuses=[],
        selected_priorities=[],
        selected_functionalities=[],
        apply_default_status_when_empty=True,
    )

    assert list(ctx.selected_statuses) == [
        "New",
        "Analysing",
        "In Progress",
        "To Rework",
        "Blocked",
        "Test",
        "Ready to Verify",
    ]
    assert "Discarded" not in ctx.selected_statuses
