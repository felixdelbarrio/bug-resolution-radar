from __future__ import annotations

import html
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import priority_rank


def render_issue_cards(dff: pd.DataFrame, *, max_cards: int, title: str) -> None:
    """Render issues as BBVA-styled cards (open issues prioritized)."""
    st.markdown(f"### {title}")

    if dff is None or dff.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

    cols = [
        "key",
        "summary",
        "status",
        "priority",
        "assignee",
        "created",
        "updated",
        "resolved",
        "url",
    ]
    safe_df = dff.copy()
    for c in cols:
        if c not in safe_df.columns:
            safe_df[c] = None

    now = pd.Timestamp.utcnow()
    open_df = (
        safe_df[safe_df["resolved"].isna()].copy()
        if "resolved" in safe_df.columns
        else safe_df.copy()
    )

    if "created" in open_df.columns:
        open_df["open_age_days"] = ((now - open_df["created"]).dt.total_seconds() / 86400.0).fillna(
            0.0
        )
    else:
        open_df["open_age_days"] = 0.0

    # Sort: priority, then updated desc.
    open_df["_prio_rank"] = (
        open_df["priority"].astype(str).map(priority_rank) if "priority" in open_df.columns else 99
    )
    sort_cols = ["_prio_rank"]
    asc = [True]
    if "updated" in open_df.columns:
        sort_cols.append("updated")
        asc.append(False)

    open_df = open_df.sort_values(by=sort_cols, ascending=asc).head(max_cards)

    for row in open_df.itertuples(index=False):
        key = html.escape(str(getattr(row, "key", "") or ""))
        url = html.escape(str(getattr(row, "url", "") or ""))
        summary = html.escape(str(getattr(row, "summary", "") or ""))
        status = html.escape(str(getattr(row, "status", "") or ""))
        prio = html.escape(str(getattr(row, "priority", "") or ""))
        assignee = html.escape(str(getattr(row, "assignee", "") or ""))
        age = float(getattr(row, "open_age_days", 0.0) or 0.0)

        badges: List[str] = []
        if prio:
            badges.append(f'<span class="badge badge-priority">Priority: {prio}</span>')
        if status:
            badges.append(f'<span class="badge badge-status">Status: {status}</span>')
        if assignee:
            badges.append(f'<span class="badge">Assignee: {assignee}</span>')
        badges.append(f'<span class="badge badge-age">Open age: {age:.0f}d</span>')

        st.markdown(
            f"""
            <div class="issue-card">
              <div class="issue-top">
                <div class="issue-key"><a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a></div>
              </div>
              <div class="issue-summary">{summary}</div>
              <div class="badges">{''.join(badges)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")


def render_issue_table(dff: pd.DataFrame) -> None:
    """Render issues as a dataframe table with a clickable Jira link column."""
    if dff is None or dff.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

    display_df = dff.copy()

    # Make a clickable Jira link using stored URL
    if "url" in display_df.columns:
        display_df["jira"] = display_df["url"]

    show_cols = [
        "jira",
        "summary",
        "status",
        "type",
        "priority",
        "created",
        "updated",
        "resolved",
        "assignee",
        "components",
        "labels",
    ]
    show_cols = [c for c in show_cols if c in display_df.columns]

    column_config: Dict[str, Any] = {}
    if "jira" in show_cols:
        column_config["jira"] = st.column_config.LinkColumn(
            "Jira",
            display_text=r".*/browse/(.*)",
        )

    sort_by = "updated" if "updated" in display_df.columns else None
    if sort_by:
        display_df = display_df.sort_values(by=sort_by, ascending=False)

    st.dataframe(
        display_df[show_cols],
        use_container_width=True,
        column_config=column_config,
    )
