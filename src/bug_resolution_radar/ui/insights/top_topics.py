"""Top topics insights grouped by functional themes."""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bug_resolution_radar.analytics.insights import (
    build_theme_fortnight_trend,
    prepare_open_theme_payload,
)
from bug_resolution_radar.config import Settings
from bug_resolution_radar.theme.design_tokens import (
    BBVA_GOAL_ACCENT_7,
    BBVA_LIGHT,
    BBVA_SIGNAL_GREEN_1,
    BBVA_SIGNAL_GREEN_2,
    BBVA_SIGNAL_GREEN_3,
    BBVA_SIGNAL_ORANGE_1,
    BBVA_SIGNAL_ORANGE_2,
    BBVA_SIGNAL_RED_1,
    BBVA_SIGNAL_RED_2,
    BBVA_SIGNAL_YELLOW_1,
    hex_to_rgba,
)
from bug_resolution_radar.ui.cache import cached_by_signature, dataframe_signature
from bug_resolution_radar.ui.common import normalize_text_col, priority_rank
from bug_resolution_radar.ui.dashboard.exports.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)
from bug_resolution_radar.ui.insights.chips import (
    inject_insights_chip_css,
    issue_cards_html_from_df,
    neutral_chip_html,
    priority_chip_html,
    status_chip_html,
)
from bug_resolution_radar.ui.insights.engine import build_topic_brief
from bug_resolution_radar.ui.insights.header_actions import render_insights_header_row
from bug_resolution_radar.ui.insights.helpers import (
    as_naive_utc,
    build_issue_lookup,
    col_exists,
    open_only,
    safe_df,
)
from bug_resolution_radar.ui.insights.learning_store import (
    LEARNING_INTERACTIONS_KEY,
    ensure_learning_session_loaded,
)
from bug_resolution_radar.ui.style import apply_plotly_bbva


def _ordered_unique_labels(values: list[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        label = str(raw or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out


def _signal_palette(*, dark_mode: bool) -> tuple[str, ...]:
    if dark_mode:
        return (
            BBVA_SIGNAL_RED_2,
            BBVA_SIGNAL_ORANGE_2,
            BBVA_SIGNAL_YELLOW_1,
            BBVA_SIGNAL_GREEN_2,
            BBVA_SIGNAL_GREEN_3,
            BBVA_LIGHT.electric_blue,
            BBVA_LIGHT.serene_blue,
            BBVA_GOAL_ACCENT_7,
            BBVA_LIGHT.aqua,
            BBVA_LIGHT.white,
        )
    return (
        BBVA_SIGNAL_RED_1,
        BBVA_SIGNAL_ORANGE_1,
        BBVA_SIGNAL_ORANGE_2,
        BBVA_SIGNAL_GREEN_1,
        BBVA_SIGNAL_GREEN_2,
        BBVA_LIGHT.electric_blue,
        BBVA_LIGHT.core_blue,
        BBVA_GOAL_ACCENT_7,
        BBVA_LIGHT.serene_dark_blue,
        BBVA_LIGHT.midnight,
    )


def _topic_selection_token(*, topic: str, total_open: int) -> str:
    status = ",".join(sorted([str(x) for x in list(st.session_state.get(FILTER_STATUS_KEY) or [])]))
    priority = ",".join(
        sorted([str(x) for x in list(st.session_state.get(FILTER_PRIORITY_KEY) or [])])
    )
    assignee = ",".join(
        sorted([str(x) for x in list(st.session_state.get(FILTER_ASSIGNEE_KEY) or [])])
    )
    nonce = int(st.session_state.get(LEARNING_INTERACTIONS_KEY, 0) or 0)
    return f"{topic}|{total_open}|{status}|{priority}|{assignee}|{nonce}"


def _rank_topic_candidates(sub: pd.DataFrame) -> pd.DataFrame:
    work = sub.copy(deep=False)
    n = len(work)
    if n == 0:
        return work

    work["__prio_rank"] = (
        work["priority"].astype(str).map(priority_rank).fillna(99).astype(int)
        if col_exists(work, "priority")
        else 99
    )
    age = pd.Series([0.0] * n, index=work.index, dtype=float)
    if col_exists(work, "__age_days"):
        age = pd.to_numeric(work["__age_days"], errors="coerce").fillna(0.0).astype(float)

    stale = pd.Series([0.0] * n, index=work.index, dtype=float)
    if col_exists(work, "updated"):
        updated_dt = pd.to_datetime(work["updated"], errors="coerce", utc=True)
        updated_naive = as_naive_utc(updated_dt)
        now = pd.Timestamp.utcnow().tz_localize(None)
        stale = ((now - updated_naive).dt.total_seconds() / 86400.0).fillna(0.0).clip(lower=0.0)

    no_owner_bonus = (
        work["assignee"].astype(str).eq("(sin asignar)").astype(float) * 4.0
        if col_exists(work, "assignee")
        else 0.0
    )
    critical_bonus = (work["__prio_rank"] <= 2).astype(float) * 24.0 + (
        work["__prio_rank"] == 3
    ).astype(float) * 10.0
    work["__topic_score"] = (
        critical_bonus
        + (age.clip(upper=180.0) * 0.22)
        + (stale.clip(upper=90.0) * 0.18)
        + no_owner_bonus
    )
    return work.sort_values(["__topic_score", "__age_days"], ascending=[False, False])


def _rotate_topic_tail(df: pd.DataFrame, *, topic: str, total_open: int) -> pd.DataFrame:
    if df.empty:
        return df
    token = _topic_selection_token(topic=topic, total_open=total_open)
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()
    offset = int(digest[:8], 16) % len(df)
    if offset == 0:
        return df
    return pd.concat([df.iloc[offset:], df.iloc[:offset]], axis=0)


def _prepare_top_topics_payload(open_df: pd.DataFrame) -> dict[str, Any]:
    base_payload = prepare_open_theme_payload(open_df, top_n=10)
    tmp_open = base_payload.get("tmp_open")
    if not isinstance(tmp_open, pd.DataFrame):
        tmp_open = pd.DataFrame()
    else:
        tmp_open = tmp_open.copy(deep=False)
    tmp_open["status"] = (
        normalize_text_col(tmp_open["status"], "(sin estado)")
        if col_exists(tmp_open, "status")
        else "(sin estado)"
    )
    tmp_open["priority"] = (
        normalize_text_col(tmp_open["priority"], "(sin priority)")
        if col_exists(tmp_open, "priority")
        else "(sin priority)"
    )
    tmp_open["summary"] = (
        tmp_open["summary"].fillna("").astype(str) if col_exists(tmp_open, "summary") else ""
    )
    tmp_open["assignee"] = (
        normalize_text_col(tmp_open["assignee"], "(sin asignar)")
        if col_exists(tmp_open, "assignee")
        else "(sin asignar)"
    )
    if col_exists(tmp_open, "created"):
        created_dt = pd.to_datetime(tmp_open["created"], errors="coerce", utc=True)
        created_naive = as_naive_utc(created_dt)
        now = pd.Timestamp.utcnow().tz_localize(None)
        tmp_open["__age_days"] = ((now - created_naive).dt.total_seconds() / 86400.0).clip(
            lower=0.0
        )
    else:
        tmp_open["__age_days"] = pd.NA

    top_tbl = base_payload.get("top_tbl")
    if not isinstance(top_tbl, pd.DataFrame):
        top_tbl = pd.DataFrame(columns=["tema", "open_count", "pct_open"])
    return {"tmp_open": tmp_open, "top_tbl": top_tbl}


def _theme_color_map(*, theme_order: list[str], dark_mode: bool) -> dict[str, str]:
    out: dict[str, str] = {}
    palette = _signal_palette(dark_mode=dark_mode)
    for idx, theme in enumerate(theme_order):
        out[theme] = palette[idx % len(palette)]
    return out


def _inject_topic_expander_color_css(
    *,
    container_key: str,
    color_hex: str,
    dark_mode: bool,
) -> None:
    tint = hex_to_rgba(color_hex, 0.30 if dark_mode else 0.22, fallback=color_hex)
    st.markdown(
        f"""
        <style>
          .st-key-{container_key} div[data-testid="stExpander"] {{
            box-shadow:
              inset 4px 0 0 {color_hex},
              inset 0 0 0 1px {tint};
          }}
          .st-key-{container_key} div[data-testid="stExpander"] summary p {{
            color: {color_hex} !important;
            font-weight: 700 !important;
          }}
          .st-key-{container_key} div[data-testid="stExpander"] summary svg {{
            color: {color_hex} !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_theme_fortnight_chart(
    *,
    trend_df: pd.DataFrame,
    cumulative: bool,
    theme_order: list[str],
    theme_color_map: dict[str, str],
) -> None:
    if trend_df.empty:
        return

    axis = (
        trend_df.loc[:, ["quincena_start", "quincena_label"]]
        .drop_duplicates(subset=["quincena_start"])
        .sort_values("quincena_start", ascending=True)
    )
    if axis.empty:
        return

    present = set(trend_df["tema"].astype(str).tolist())
    theme_order = [t for t in theme_order if t in present]
    if not theme_order:
        theme_order = _ordered_unique_labels(trend_df["tema"].tolist())
    if not theme_order:
        return

    y_title = "Incidencias acumuladas" if cumulative else "Incidencias"
    fig = go.Figure()
    for theme in theme_order:
        sub = trend_df.loc[trend_df["tema"] == theme].sort_values("quincena_start", ascending=True)
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["quincena_start"],
                y=sub["issues_value"],
                mode="lines+markers",
                name=theme,
                line=dict(color=theme_color_map.get(theme), width=2.8 if cumulative else 2.3),
                marker=dict(size=7),
                customdata=sub[["quincena_label"]],
                hovertemplate=(
                    "Tema: %{fullData.name}<br>"
                    "Quincena: %{customdata[0]}<br>"
                    f"{y_title}: %{{y}}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        height=380,
        margin=dict(l=16, r=16, t=18, b=170),
        xaxis_title="Quincena",
        yaxis_title=y_title,
        hovermode="x unified",
        xaxis_title_standoff=18,
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=axis["quincena_start"],
        ticktext=axis["quincena_label"],
        tickangle=-26,
    )
    fig = apply_plotly_bbva(fig, showlegend=True)
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.54,
            xanchor="center",
            x=0.5,
            title=dict(text=""),
        ),
        margin=dict(l=16, r=16, t=18, b=170),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_top_topics_tab(
    *,
    settings: Settings,
    dff_filtered: pd.DataFrame,
    dff_history: pd.DataFrame | None = None,
    kpis: Dict[str, Any],
    use_accumulated_scope: bool = False,
    header_left_render: Callable[[], None] | None = None,
) -> None:
    """
    Tab: Top temas funcionales (abiertas)
    - Agrupa por macro-tema (Softoken, Crédito, Monetarias, Tareas, ...)
    - Muestra expander por tema con lista de issues (key clickable) + estado + prioridad
    """
    _ = kpis  # maintained in signature for compatibility with caller
    inject_insights_chip_css()
    ensure_learning_session_loaded(settings=settings)

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    open_df = open_only(dff)
    total_open = int(len(open_df)) if open_df is not None else 0
    if total_open == 0:
        st.info("No hay incidencias abiertas para analizar temas.")
        return

    today = pd.Timestamp.utcnow().tz_localize(None).strftime("%Y-%m-%d")
    sig = dataframe_signature(
        open_df,
        columns=("key", "summary", "status", "priority", "assignee", "created", "updated"),
        salt=f"insights.top_topics.v1:{today}",
    )
    payload, _ = cached_by_signature(
        "insights.top_topics",
        sig,
        lambda: _prepare_top_topics_payload(open_df),
        max_entries=12,
    )
    tmp_open = payload.get("tmp_open")
    top_tbl = payload.get("top_tbl")
    if not isinstance(tmp_open, pd.DataFrame):
        tmp_open = pd.DataFrame()
    if not isinstance(top_tbl, pd.DataFrame):
        top_tbl = pd.DataFrame(columns=["tema", "open_count", "pct_open"])
    if top_tbl.empty:
        st.info("No hay columna `summary` para construir temas.")
        return

    key_to_url, key_to_meta = build_issue_lookup(open_df, settings=settings)
    render_insights_header_row(
        left_render=header_left_render,
        right_render=lambda: render_minimal_export_actions(
            key_prefix="insights::top_topics",
            filename_prefix="insights_temas",
            suffix="top_temas",
            csv_df=top_tbl.copy(deep=False),
        ),
    )
    history_source = safe_df(dff_history) if isinstance(dff_history, pd.DataFrame) else dff
    history_open = open_only(history_source)
    selected_themes = _ordered_unique_labels(top_tbl["tema"].tolist())
    dark_mode = bool(st.session_state.get("workspace_dark_mode", False))
    topic_color_map = _theme_color_map(theme_order=selected_themes, dark_mode=dark_mode)
    trend_df = pd.DataFrame(
        columns=[
            "quincena_start",
            "quincena_end",
            "quincena_label",
            "tema",
            "issues",
            "issues_cumulative",
            "issues_value",
        ]
    )
    if not history_open.empty and selected_themes:
        theme_token = "|".join(selected_themes)
        trend_sig = dataframe_signature(
            history_open,
            columns=("summary", "created", "status", "resolved"),
            salt=(
                f"insights.top_topics.fortnight.v1:{int(bool(use_accumulated_scope))}:{theme_token}"
            ),
        )
        trend_payload, _ = cached_by_signature(
            "insights.top_topics.fortnight",
            trend_sig,
            lambda: build_theme_fortnight_trend(
                history_open,
                theme_whitelist=selected_themes,
                cumulative=bool(use_accumulated_scope),
            ),
            max_entries=12,
        )
        if isinstance(trend_payload, pd.DataFrame):
            trend_df = trend_payload

    if not trend_df.empty:
        _render_theme_fortnight_chart(
            trend_df=trend_df,
            cumulative=bool(use_accumulated_scope),
            theme_order=selected_themes,
            theme_color_map=topic_color_map,
        )
    else:
        st.caption(
            "No hay histórico suficiente para construir la tendencia quincenal por funcionalidad."
        )

    for idx, (_, r) in enumerate(top_tbl.iterrows()):
        topic = str(r.get("tema", "") or "").strip()
        cnt = int(r.get("open_count", 0) or 0)
        pct_txt = f"{float(r.get('pct_open', 0.0) or 0.0):.1f}%"
        sub = tmp_open[tmp_open["__theme"] == topic].copy(deep=False)
        topic_color = topic_color_map.get(topic, BBVA_LIGHT.serene_blue)

        st_dom = (
            sub["status"].value_counts().index[0]
            if (not sub.empty and "status" in sub.columns)
            else "-"
        )
        pr_dom = (
            sub["priority"].value_counts().index[0]
            if (not sub.empty and "priority" in sub.columns)
            else "-"
        )

        hdr = f"**{cnt} issues** · **{pct_txt}** · {topic}"

        container_key = f"insights_topic_block_{idx}"
        with st.container(key=container_key):
            _inject_topic_expander_color_css(
                container_key=container_key,
                color_hex=topic_color,
                dark_mode=dark_mode,
            )
            with st.expander(hdr, expanded=False):
                st.markdown(
                    (
                        '<div class="ins-meta-row">'
                        f"{neutral_chip_html(f'{cnt} issues')}"
                        f"{neutral_chip_html(pct_txt)}"
                        f"{status_chip_html(st_dom)}"
                        f"{priority_chip_html(pr_dom)}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                st.caption(build_topic_brief(topic=topic, sub_df=sub, total_open=total_open))
                if sub.empty or not col_exists(sub, "key"):
                    st.caption("No se han podido mapear issues individuales para este tema.")
                    continue

                ranked = _rank_topic_candidates(sub)
                anchor = ranked.head(8)
                tail = ranked.iloc[8:]
                if not tail.empty:
                    tail = _rotate_topic_tail(tail, topic=topic, total_open=total_open)
                sub_view = pd.concat([anchor, tail], axis=0).head(20)

                cards_html = issue_cards_html_from_df(
                    sub_view,
                    key_to_url=key_to_url,
                    key_to_meta=key_to_meta,
                    summary_col="summary",
                    assignee_col="assignee",
                    age_days_col="__age_days",
                    summary_max_chars=160,
                    limit=20,
                )
                if cards_html:
                    st.markdown(cards_html, unsafe_allow_html=True)

    st.caption(
        "Tip: el % indica el peso real de cada tema y el orden de casos se ajusta segun filtros e interacciones."
    )
