"""Top topics insights grouped by functional themes."""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any, Callable, Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bug_resolution_radar.analytics.insights import (
    build_theme_daily_trend,
    build_theme_fortnight_trend,
    is_other_theme_label,
    order_theme_labels_by_volume,
    prepare_open_theme_payload,
    sort_theme_table_by_volume,
)
from bug_resolution_radar.config import Settings
from bug_resolution_radar.theme.design_tokens import (
    BBVA_DARK,
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


def _is_others_label(value: object) -> bool:
    return is_other_theme_label(value)


def _sort_topics_by_volume_with_others_last(top_tbl: pd.DataFrame) -> pd.DataFrame:
    return sort_theme_table_by_volume(top_tbl, label_col="tema", count_col="open_count")


def _stacked_theme_order(
    theme_order: list[str],
    *,
    theme_count_by_label: dict[str, int] | None = None,
) -> list[str]:
    ordered = order_theme_labels_by_volume(
        theme_order,
        counts_by_label=theme_count_by_label,
        others_last=True,
    )
    if not ordered:
        return []
    non_other = [theme for theme in ordered if not _is_others_label(theme)]
    other = [theme for theme in ordered if _is_others_label(theme)]
    return non_other + other


def _priority_ordered_topics(top_tbl: pd.DataFrame, *, tmp_open: pd.DataFrame) -> pd.DataFrame:
    """Order functional topics prioritizing business criticality over raw volume."""
    if not isinstance(top_tbl, pd.DataFrame) or top_tbl.empty:
        return top_tbl

    ordered = _sort_topics_by_volume_with_others_last(top_tbl)
    ordered["tema"] = ordered["tema"].astype(str)
    ordered["open_count"] = (
        pd.to_numeric(ordered["open_count"], errors="coerce").fillna(0).astype(int)
    )

    if (
        not isinstance(tmp_open, pd.DataFrame)
        or tmp_open.empty
        or not col_exists(tmp_open, "__theme")
    ):
        return ordered.reset_index(drop=True)

    if col_exists(tmp_open, "priority"):
        prio_rank = tmp_open["priority"].astype(str).map(priority_rank).fillna(99).astype(int)
    else:
        prio_rank = pd.Series([99] * len(tmp_open), index=tmp_open.index, dtype=int)

    prio_source = pd.DataFrame(
        {
            "tema": tmp_open["__theme"].astype(str),
            "__prio_rank": prio_rank,
        }
    )
    prio_stats = (
        prio_source.groupby("tema", dropna=False)
        .agg(
            __best_prio=("__prio_rank", "min"),
            __critical_cnt=("__prio_rank", lambda s: int((s <= 2).sum())),
            __avg_prio=("__prio_rank", "mean"),
        )
        .reset_index()
    )

    merged = ordered.merge(prio_stats, on="tema", how="left")
    merged["__best_prio"] = (
        pd.to_numeric(merged["__best_prio"], errors="coerce").fillna(99).astype(int)
    )
    merged["__critical_cnt"] = (
        pd.to_numeric(merged["__critical_cnt"], errors="coerce").fillna(0).astype(int)
    )
    merged["__avg_prio"] = pd.to_numeric(merged["__avg_prio"], errors="coerce").fillna(99.0)
    merged["__is_others"] = merged["tema"].map(_is_others_label)

    merged = merged.sort_values(
        ["__is_others", "__best_prio", "__critical_cnt", "open_count", "__avg_prio", "tema"],
        ascending=[True, True, False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return merged.drop(
        columns=["__best_prio", "__critical_cnt", "__avg_prio", "__is_others"],
        errors="ignore",
    )


def _normalize_theme_key(value: object) -> str:
    txt = str(value or "").strip().lower()
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    return "".join(ch for ch in txt if not unicodedata.combining(ch))


def _signal_palette(*, dark_mode: bool) -> tuple[str, ...]:
    if dark_mode:
        return (
            BBVA_SIGNAL_RED_2,
            BBVA_LIGHT.electric_blue,
            BBVA_SIGNAL_ORANGE_2,
            BBVA_GOAL_ACCENT_7,
            BBVA_SIGNAL_YELLOW_1,
            BBVA_LIGHT.aqua,
            BBVA_SIGNAL_GREEN_2,
            BBVA_LIGHT.serene_blue,
            BBVA_SIGNAL_GREEN_3,
            BBVA_LIGHT.white,
        )
    return (
        BBVA_SIGNAL_RED_1,
        BBVA_LIGHT.electric_blue,
        BBVA_SIGNAL_ORANGE_1,
        BBVA_GOAL_ACCENT_7,
        BBVA_SIGNAL_YELLOW_1,
        BBVA_LIGHT.aqua,
        BBVA_SIGNAL_GREEN_1,
        BBVA_LIGHT.royal_blue,
        BBVA_LIGHT.serene_blue,
        BBVA_LIGHT.core_blue,
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
    return work.sort_values(
        ["__prio_rank", "__topic_score", "__age_days"],
        ascending=[True, False, False],
    )


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
    semantic_map = (
        {
            "pagos": BBVA_SIGNAL_RED_2,
            "tareas": BBVA_SIGNAL_ORANGE_2,
            "monetarias": BBVA_SIGNAL_YELLOW_1,
            "credito": BBVA_SIGNAL_GREEN_2,
            "login y acceso": BBVA_LIGHT.electric_blue,
            "softoken": BBVA_GOAL_ACCENT_7,
            "transferencias": BBVA_LIGHT.serene_blue,
            "notificaciones": BBVA_LIGHT.aqua,
        }
        if dark_mode
        else {
            "pagos": BBVA_SIGNAL_RED_1,
            "tareas": BBVA_SIGNAL_ORANGE_1,
            "monetarias": BBVA_SIGNAL_YELLOW_1,
            "credito": BBVA_SIGNAL_GREEN_1,
            "login y acceso": BBVA_LIGHT.electric_blue,
            "softoken": BBVA_GOAL_ACCENT_7,
            "transferencias": BBVA_LIGHT.serene_blue,
            "notificaciones": BBVA_LIGHT.aqua,
        }
    )
    fallback_idx = 0
    used_colors: set[str] = set()
    others_color = BBVA_DARK.ink_muted if dark_mode else BBVA_LIGHT.ink_muted
    for theme in theme_order:
        norm_theme = _normalize_theme_key(theme)
        if norm_theme == "otros":
            out[theme] = others_color
            used_colors.add(others_color)
            continue
        token_color = semantic_map.get(norm_theme, "")
        if token_color:
            out[theme] = token_color
            used_colors.add(token_color)
            continue
        if not palette:
            out[theme] = BBVA_LIGHT.serene_blue
            continue
        for _ in range(len(palette)):
            candidate = palette[fallback_idx % len(palette)]
            fallback_idx += 1
            if candidate in used_colors:
                continue
            out[theme] = candidate
            used_colors.add(candidate)
            break
        if theme not in out:
            out[theme] = palette[fallback_idx % len(palette)]
            fallback_idx += 1
    return out


def _hex_luminance(hex_color: str) -> float:
    token = str(hex_color or "").strip().lstrip("#")
    if len(token) != 6:
        return 0.0
    try:
        r = int(token[0:2], 16) / 255.0
        g = int(token[2:4], 16) / 255.0
        b = int(token[4:6], 16) / 255.0
    except ValueError:
        return 0.0
    return (0.2126 * r) + (0.7152 * g) + (0.0722 * b)


def _segment_text_color(fill_hex: str, *, dark_mode: bool) -> str:
    lum = _hex_luminance(fill_hex)
    if lum >= (0.58 if dark_mode else 0.64):
        return BBVA_LIGHT.midnight
    return BBVA_LIGHT.white


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


def _render_theme_trend_chart(
    *,
    trend_df: pd.DataFrame,
    theme_order: list[str],
    theme_color_map: dict[str, str],
    theme_count_by_label: dict[str, int] | None = None,
    x_col: str,
    x_label_col: str,
    x_title: str,
    y_title: str,
    tick_angle: int,
) -> None:
    if trend_df.empty:
        return

    axis = (
        trend_df.loc[:, [x_col, x_label_col]]
        .drop_duplicates(subset=[x_col])
        .sort_values(x_col, ascending=True)
    )
    if axis.empty:
        return

    present = set(trend_df["tema"].astype(str).tolist())
    theme_order = [t for t in theme_order if t in present]
    if not theme_order:
        totals = trend_df["tema"].value_counts()
        theme_order = order_theme_labels_by_volume(
            totals.index.tolist(),
            counts_by_label=totals,
            others_last=True,
        )
    if not theme_order:
        return

    theme_order = _stacked_theme_order(
        theme_order,
        theme_count_by_label=theme_count_by_label,
    )
    if not theme_order:
        return

    dark_mode = bool(st.session_state.get("workspace_dark_mode", False))
    # Plotly stacks bars in insertion order (bottom -> top).
    # This order is normalized to always keep non-"Otros" themes first by volume
    # and "Otros" as the topmost (last) segment.
    stacked_order = list(theme_order)
    axis_labels = axis[x_label_col].astype(str).tolist()
    total_by_label = (
        trend_df.groupby(x_label_col, as_index=True)["issues_value"]
        .sum()
        .reindex(axis_labels, fill_value=0.0)
    )

    fig = go.Figure()
    for theme in stacked_order:
        sub = trend_df.loc[trend_df["tema"] == theme].sort_values(x_col, ascending=True)
        if sub.empty:
            continue
        values = pd.to_numeric(sub["issues_value"], errors="coerce").fillna(0.0).tolist()
        labels = sub[x_label_col].astype(str).tolist()
        total_custom = [[int(total_by_label.get(lbl, 0.0))] for lbl in labels]
        text_vals = [str(int(v)) if float(v) > 0 else "" for v in values]
        color_hex = str(theme_color_map.get(theme) or BBVA_LIGHT.serene_blue)
        fig.add_trace(
            go.Bar(
                x=labels,
                y=values,
                name=theme,
                marker=dict(color=color_hex),
                text=text_vals,
                textposition="inside",
                textfont=dict(color=_segment_text_color(color_hex, dark_mode=dark_mode), size=11),
                customdata=total_custom,
                legendrank=int(theme_order.index(theme)),
                hovertemplate=(
                    "Tema: %{fullData.name}<br>"
                    f"{x_title}: %{{x}}<br>"
                    f"{y_title}: %{{y}}<br>"
                    "Total columna: %{customdata[0]}<extra></extra>"
                ),
            )
        )

    max_total = float(total_by_label.max()) if not total_by_label.empty else 0.0
    total_offset = max(max_total * 0.055, 0.16)
    total_text = [f"{int(v)}" for v in total_by_label.tolist()]
    fig.add_trace(
        go.Scatter(
            x=axis_labels,
            y=[float(v) + total_offset for v in total_by_label.tolist()],
            mode="text",
            text=total_text,
            textposition="top center",
            showlegend=False,
            hoverinfo="skip",
            textfont=dict(size=12, color=BBVA_LIGHT.white if dark_mode else BBVA_LIGHT.midnight),
        )
    )

    fig.update_layout(
        height=380,
        margin=dict(l=16, r=16, t=18, b=170),
        xaxis_title=x_title,
        yaxis_title=y_title,
        hovermode="x",
        xaxis_title_standoff=18,
        barmode="stack",
        bargap=0.20,
        uniformtext=dict(minsize=10, mode="hide"),
    )
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=axis_labels,
        tickangle=tick_angle,
    )
    fig.update_yaxes(range=[0, max_total + (total_offset * 2.3) if max_total > 0 else 1.0])
    fig = apply_plotly_bbva(fig, showlegend=True)
    for trace in list(getattr(fig, "data", []) or []):
        try:
            if str(getattr(trace, "type", "")).strip().lower() != "bar":
                continue
            trace_name = str(getattr(trace, "name", "") or "").strip()
            if not trace_name:
                continue
            fill = str(theme_color_map.get(trace_name) or "")
            if not fill:
                continue
            trace.textfont = dict(color=_segment_text_color(fill, dark_mode=dark_mode), size=11)
        except Exception:
            continue
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.54,
            xanchor="center",
            x=0.5,
            traceorder="normal",
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
    top_tbl = _sort_topics_by_volume_with_others_last(top_tbl)
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
    selected_themes = order_theme_labels_by_volume(
        top_tbl["tema"].tolist(),
        counts_by_label=dict(
            zip(
                top_tbl["tema"].astype(str).tolist(),
                pd.to_numeric(top_tbl["open_count"], errors="coerce")
                .fillna(0)
                .astype(int)
                .tolist(),
            )
        ),
        others_last=True,
    )
    theme_count_by_label = dict(
        zip(
            top_tbl["tema"].astype(str).tolist(),
            pd.to_numeric(top_tbl["open_count"], errors="coerce").fillna(0).astype(int).tolist(),
        )
    )
    dark_mode = bool(st.session_state.get("workspace_dark_mode", False))
    topic_color_map = _theme_color_map(theme_order=selected_themes, dark_mode=dark_mode)
    trend_df = pd.DataFrame()
    trend_mode_label = "diaria"
    if use_accumulated_scope:
        history_source = safe_df(dff_history) if isinstance(dff_history, pd.DataFrame) else dff
        history_open = open_only(history_source)
        if not history_open.empty and selected_themes:
            theme_token = "|".join(selected_themes)
            trend_sig = dataframe_signature(
                history_open,
                columns=("summary", "created", "status", "resolved"),
                salt=f"insights.top_topics.fortnight.v2:1:{theme_token}",
            )
            trend_payload, _ = cached_by_signature(
                "insights.top_topics.fortnight",
                trend_sig,
                lambda: build_theme_fortnight_trend(
                    history_open,
                    theme_whitelist=selected_themes,
                    cumulative=True,
                ),
                max_entries=12,
            )
            if isinstance(trend_payload, pd.DataFrame):
                trend_df = trend_payload
        trend_mode_label = "quincenal acumulada"
    else:
        daily_source = open_df
        if not daily_source.empty and selected_themes:
            theme_token = "|".join(selected_themes)
            trend_sig = dataframe_signature(
                daily_source,
                columns=("summary", "created", "status", "resolved"),
                salt=f"insights.top_topics.daily.v1:{theme_token}",
            )
            trend_payload, _ = cached_by_signature(
                "insights.top_topics.daily",
                trend_sig,
                lambda: build_theme_daily_trend(
                    daily_source,
                    theme_whitelist=selected_themes,
                ),
                max_entries=12,
            )
            if isinstance(trend_payload, pd.DataFrame):
                trend_df = trend_payload
        trend_mode_label = "diaria de la quincena analizada"

    if not trend_df.empty:
        if use_accumulated_scope:
            _render_theme_trend_chart(
                trend_df=trend_df,
                theme_order=selected_themes,
                theme_color_map=topic_color_map,
                theme_count_by_label=theme_count_by_label,
                x_col="quincena_start",
                x_label_col="quincena_label",
                x_title="Quincena",
                y_title="Incidencias abiertas acumuladas",
                tick_angle=-26,
            )
        else:
            _render_theme_trend_chart(
                trend_df=trend_df,
                theme_order=selected_themes,
                theme_color_map=topic_color_map,
                theme_count_by_label=theme_count_by_label,
                x_col="date",
                x_label_col="date_label",
                x_title="Día",
                y_title="Incidencias abiertas",
                tick_angle=-35,
            )
    else:
        st.caption(f"No hay histórico suficiente para construir la tendencia {trend_mode_label}.")

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
