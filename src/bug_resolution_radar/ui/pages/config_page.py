"""Configuration page to manage data sources and visualization preferences."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bug_resolution_radar.analytics.analysis_window import (
    max_available_backlog_months,
    parse_analysis_lookback_months,
)
from bug_resolution_radar.analytics.period_summary import (
    OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH,
    OPEN_ISSUES_FOCUS_MODE_MAESTRAS,
    normalize_open_issues_focus_mode,
)
from bug_resolution_radar.config import (
    LEGACY_ENV_KEYS_TO_PRUNE,
    Settings,
    all_configured_sources,
    build_source_id,
    country_rollup_sources,
    helix_sources,
    jira_sources,
    normalize_analysis_lookback_months,
    restore_env_from_example,
    rollup_source_ids,
    save_settings,
    suggested_period_ppt_template_path,
    supported_countries,
    to_env_json,
)
from bug_resolution_radar.services.source_maintenance import (
    cache_inventory,
    purge_source_cache,
    reset_cache_store,
)
from bug_resolution_radar.theme.design_tokens import (
    BBVA_LIGHT,
    BBVA_SIGNAL_GREEN_1,
    BBVA_SIGNAL_ORANGE_1,
    BBVA_SIGNAL_RED_1,
)
from bug_resolution_radar.ui.cache import clear_signature_cache
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.dashboard.performance import (
    clear_perf_history,
    list_perf_snapshots,
    perf_history_rows,
)
from bug_resolution_radar.ui.dashboard.exports.downloads import (
    build_download_filename,
    df_to_excel_bytes,
)
from bug_resolution_radar.ui.style import apply_plotly_bbva

_DELETE_ROW_TOKEN_PREFIX = "__cfg_delete_row__:"


def _boolish(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _trend_chart_catalog() -> List[Tuple[str, str]]:
    return [
        ("timeseries", "Evolución (últimos 90 días)"),
        ("age_buckets", "Distribución antigüedad (abiertas)"),
        ("resolution_hist", "Días abiertas por prioridad"),
        ("open_priority_pie", "Issues abiertos por prioridad (pie)"),
        ("open_status_bar", "Issues por Estado (bar)"),
    ]


def _safe_update_settings(settings: Settings, update: Dict[str, Any]) -> Settings:
    allowed = set(getattr(settings.__class__, "model_fields", {}).keys())
    clean = {k: v for k, v in update.items() if k in allowed}
    return settings.model_copy(update=clean)


def _save_settings_with_migrations(settings: Settings) -> None:
    migrated = _safe_update_settings(
        settings,
        {
            "ANALYSIS_LOOKBACK_MONTHS": normalize_analysis_lookback_months(
                getattr(settings, "ANALYSIS_LOOKBACK_MONTHS", 12),
                default=12,
            ),
        },
    )
    save_settings(migrated, drop_keys=LEGACY_ENV_KEYS_TO_PRUNE)


def _parse_csv_ids(raw: object, valid_ids: List[str]) -> List[str]:
    txt = str(raw or "").strip()
    if not txt:
        return []
    out: List[str] = []
    for x in txt.split(","):
        v = x.strip()
        if v and v in valid_ids and v not in out:
            out.append(v)
    return out


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _render_purge_stats(stats: Dict[str, int]) -> None:
    issues_removed = int(stats.get("issues_removed", 0) or 0)
    helix_items_removed = int(stats.get("helix_items_removed", 0) or 0)
    learning_scopes_removed = int(stats.get("learning_scopes_removed", 0) or 0)
    st.info(
        "Cache saneado. "
        f"Issues purgados: {issues_removed}. "
        f"Items Helix purgados: {helix_items_removed}. "
        f"Scopes de aprendizaje purgados: {learning_scopes_removed}."
    )


def _source_rows_export_df(df: pd.DataFrame, *, source_type: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    rows_out: List[Dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        row_copy = dict(row)
        row_copy.pop("__delete__", None)

        country = _as_str(row_copy.get("country"))
        alias = _as_str(row_copy.get("alias"))
        source_id = _as_str(row_copy.get("__source_id__"))
        if not source_id and country and alias:
            source_id = build_source_id(source_type, country, alias)

        business_fields = {
            str(k): _as_str(v)
            for k, v in row_copy.items()
            if k != "__source_id__" and not str(k).startswith("__")
        }
        if not any(business_fields.values()):
            continue

        export_row: Dict[str, Any] = {"source_id": source_id}
        export_row.update(business_fields)
        rows_out.append(export_row)

    if not rows_out:
        return pd.DataFrame()

    out_df = pd.DataFrame(rows_out)
    preferred_cols = ["source_id", "country", "alias"]
    ordered_cols = [c for c in preferred_cols if c in out_df.columns] + [
        c for c in out_df.columns if c not in preferred_cols
    ]
    return out_df.loc[:, ordered_cols].copy(deep=False)


def _render_sources_excel_download(
    df: pd.DataFrame,
    *,
    source_type: str,
    key: str,
    filename_prefix: str,
    sheet_name: str,
) -> None:
    export_df = _source_rows_export_df(df, source_type=source_type)
    disabled = export_df.empty
    payload = (
        b""
        if disabled
        else df_to_excel_bytes(export_df, include_index=False, sheet_name=sheet_name)
    )
    st.download_button(
        label="Descargar Excel",
        data=payload,
        file_name=build_download_filename(filename_prefix, suffix="fuentes", ext="xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key,
        disabled=disabled,
        width="stretch",
    )


def _merge_purge_stats(acc: Dict[str, int], nxt: Dict[str, int]) -> Dict[str, int]:
    return {
        "issues_removed": int(acc.get("issues_removed", 0) or 0)
        + int(nxt.get("issues_removed", 0) or 0),
        "helix_items_removed": int(acc.get("helix_items_removed", 0) or 0)
        + int(nxt.get("helix_items_removed", 0) or 0),
        "learning_scopes_removed": int(acc.get("learning_scopes_removed", 0) or 0)
        + int(nxt.get("learning_scopes_removed", 0) or 0),
    }


def _is_delete_phrase_valid(value: Any) -> bool:
    return str(value or "").strip().upper() == "ELIMINAR"


def _is_reset_phrase_valid(value: Any) -> bool:
    return str(value or "").strip().upper() == "RESETEAR"


def _is_restore_phrase_valid(value: Any) -> bool:
    return str(value or "").strip().upper() == "RESTAURAR"


def _inject_delete_zone_css() -> None:
    st.markdown(
        """
        <style>
          [class*="st-key-cfg_jira_delete_shell"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-cfg_helix_delete_shell"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-cfg_cache_cache_reset_shell"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-cfg_prefs_restore_shell"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 86%, var(--bbva-glow-soft) 14%) !important;
            background:
              radial-gradient(1200px 280px at 0% 0%, color-mix(in srgb, var(--bbva-primary) 8%, transparent), transparent 55%),
              linear-gradient(155deg, color-mix(in srgb, var(--bbva-surface) 92%, var(--bbva-midnight) 8%), var(--bbva-surface));
            box-shadow: 0 12px 28px color-mix(in srgb, var(--bbva-text) 10%, transparent) !important;
            border-radius: var(--bbva-radius-xl) !important;
          }
          .cfg-delete-chip-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: .5rem;
            margin: .2rem 0 .4rem;
          }
          .cfg-delete-chip {
            display: inline-flex;
            align-items: center;
            gap: .4rem;
            padding: .28rem .78rem;
            border-radius: 999px;
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 74%, var(--bbva-glow-soft) 26%);
            background: color-mix(in srgb, var(--bbva-surface-elevated) 84%, var(--bbva-midnight) 16%);
            color: color-mix(in srgb, var(--bbva-text) 95%, transparent);
            font-size: .91rem;
            line-height: 1.15rem;
            font-weight: 600;
          }
          .cfg-delete-chip-dot {
            width: .46rem;
            height: .46rem;
            border-radius: 50%;
            background: color-mix(in srgb, var(--bbva-primary) 76%, var(--bbva-glow-soft) 24%);
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--bbva-primary) 20%, transparent);
          }
          .cfg-delete-ghost {
            border: 1px dashed var(--bbva-border);
            border-radius: var(--bbva-radius-m);
            padding: .65rem .75rem;
            color: var(--bbva-text-muted);
            background: color-mix(in srgb, var(--bbva-surface) 96%, transparent);
            margin-bottom: .25rem;
            font-size: .92rem;
          }
          .cfg-delete-counter {
            color: color-mix(in srgb, var(--bbva-text) 86%, transparent);
            margin-bottom: .2rem;
            font-size: .92rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_preferences_zone_css() -> None:
    st.markdown(
        """
        <style>
          [class*="st-key-cfg_tabs_shell"] div[data-baseweb="tab-list"] {
            gap: .35rem;
            padding: .28rem;
            border-radius: 14px;
            background:
              linear-gradient(180deg,
                color-mix(in srgb, var(--bbva-surface-elevated) 92%, var(--bbva-midnight) 8%),
                color-mix(in srgb, var(--bbva-surface) 97%, transparent)
              );
            border: 1px solid color-mix(in srgb, var(--bbva-border) 78%, var(--bbva-glow-soft) 22%);
            box-shadow: 0 8px 22px color-mix(in srgb, var(--bbva-text) 8%, transparent);
            width: fit-content;
          }
          [class*="st-key-cfg_tabs_shell"] button[role="tab"] {
            border-radius: 11px !important;
            border: 1px solid transparent !important;
            padding-inline: .95rem !important;
            transition: border-color .18s ease, box-shadow .18s ease, background-color .18s ease;
          }
          [class*="st-key-cfg_tabs_shell"] button[role="tab"][aria-selected="true"] {
            border-color: color-mix(in srgb, var(--bbva-primary) 52%, var(--bbva-glow-soft) 48%) !important;
            box-shadow: 0 0 0 1px color-mix(in srgb, var(--bbva-primary) 10%, transparent) inset;
            background:
              linear-gradient(180deg,
                color-mix(in srgb, var(--bbva-primary) 10%, var(--bbva-surface-elevated)),
                color-mix(in srgb, var(--bbva-primary) 4%, var(--bbva-surface))
              ) !important;
          }
          [class*="st-key-cfg_prefs_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid color-mix(in srgb, var(--bbva-border) 82%, var(--bbva-glow-soft) 18%) !important;
            border-radius: 16px !important;
            padding: .35rem .55rem .5rem !important;
            background:
              radial-gradient(900px 220px at 0% 0%, color-mix(in srgb, var(--bbva-primary) 8%, transparent), transparent 60%),
              linear-gradient(165deg, color-mix(in srgb, var(--bbva-surface) 97%, var(--bbva-midnight) 3%), var(--bbva-surface));
            box-shadow: 0 10px 26px color-mix(in srgb, var(--bbva-text) 6%, transparent) !important;
            margin-bottom: .7rem;
          }
          [class*="st-key-cfg_prefs_card_"] [data-testid="stMarkdownContainer"] h4 {
            letter-spacing: -.01em;
          }
          [class*="st-key-cfg_prefs_card_ppt"] input {
            font-weight: 600;
          }
          [class*="st-key-cfg_prefs_card_favs"] [data-testid="column"] {
            align-self: end;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_performance_zone_css() -> None:
    st.markdown(
        """
        <style>
          .cfg-perf-hero {
            border: 1px solid color-mix(in srgb, var(--bbva-primary) 24%, var(--bbva-border) 76%);
            border-radius: var(--bbva-radius-xl);
            padding: 1rem 1.05rem .9rem;
            background:
              radial-gradient(820px 220px at 4% -8%, color-mix(in srgb, var(--bbva-primary) 20%, transparent), transparent 60%),
              radial-gradient(560px 160px at 100% 0%, color-mix(in srgb, var(--bbva-glow-soft) 26%, transparent), transparent 58%),
              linear-gradient(155deg, color-mix(in srgb, var(--bbva-surface-elevated) 92%, var(--bbva-midnight) 8%), var(--bbva-surface));
            box-shadow: 0 14px 34px color-mix(in srgb, var(--bbva-text) 13%, transparent);
            margin-bottom: .9rem;
          }
          .cfg-perf-title {
            font-size: 1.04rem;
            font-weight: 760;
            letter-spacing: -.01em;
            color: var(--bbva-text);
          }
          .cfg-perf-subtitle {
            margin-top: .2rem;
            color: var(--bbva-text-muted);
            font-size: .9rem;
          }
          .cfg-perf-kpi-grid {
            margin-top: .78rem;
            display: grid;
            gap: .52rem;
            grid-template-columns: repeat(4, minmax(120px, 1fr));
          }
          .cfg-perf-kpi {
            border-radius: 13px;
            border: 1px solid color-mix(in srgb, var(--bbva-border) 72%, var(--bbva-glow-soft) 28%);
            background: color-mix(in srgb, var(--bbva-surface-elevated) 86%, var(--bbva-midnight) 14%);
            padding: .62rem .72rem;
            min-height: 72px;
          }
          .cfg-perf-kpi span {
            display: block;
            font-size: .75rem;
            color: var(--bbva-text-muted);
            text-transform: uppercase;
            letter-spacing: .03em;
            font-weight: 700;
            margin-bottom: .16rem;
          }
          .cfg-perf-kpi strong {
            font-size: 1.06rem;
            color: var(--bbva-text);
            font-weight: 760;
            letter-spacing: -.01em;
          }
          .cfg-perf-view-grid {
            display: grid;
            gap: .55rem;
            grid-template-columns: repeat(2, minmax(180px, 1fr));
          }
          .cfg-perf-view-card {
            border-radius: 13px;
            padding: .7rem .8rem .66rem;
            border: 1px solid color-mix(in srgb, var(--bbva-border) 78%, var(--bbva-glow-soft) 22%);
            background:
              linear-gradient(160deg, color-mix(in srgb, var(--bbva-surface) 96%, var(--bbva-surface-2)), var(--bbva-surface));
          }
          .cfg-perf-view-card.is-ok {
            box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bbva-ok) 26%, transparent);
          }
          .cfg-perf-view-card.is-warn {
            box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--bbva-warning) 34%, transparent);
          }
          .cfg-perf-view-head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: .5rem;
          }
          .cfg-perf-view-name {
            font-weight: 740;
            color: var(--bbva-text);
            font-size: .94rem;
          }
          .cfg-perf-view-total {
            font-weight: 780;
            font-size: 1rem;
            color: var(--bbva-text);
          }
          .cfg-perf-view-meta {
            margin-top: .22rem;
            color: var(--bbva-text-muted);
            font-size: .82rem;
          }
          @media (max-width: 980px) {
            .cfg-perf-kpi-grid {
              grid-template-columns: repeat(2, minmax(120px, 1fr));
            }
            .cfg-perf-view-grid {
              grid-template-columns: repeat(1, minmax(140px, 1fr));
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _fmt_ms(value: Any) -> str:
    return f"{_safe_float(value):.0f} ms"


def _as_non_empty_text_list(value: object) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [str(x) for x in value if str(x).strip()]


def _build_perf_history_df() -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for row in perf_history_rows(limit=320):
        metrics = row.get("metrics_ms")
        budgets = row.get("budget_ms")
        metrics_map = metrics if isinstance(metrics, dict) else {}
        budgets_map = budgets if isinstance(budgets, dict) else {}
        overruns = row.get("overruns")
        overrun_list = _as_non_empty_text_list(overruns)
        overrun_count_raw = row.get("overrun_count", len(overrun_list))
        blocks = sorted([str(k) for k in metrics_map.keys()])
        rows.append(
            {
                "captured_at_utc": str(row.get("captured_at_utc", "") or ""),
                "view": str(row.get("view", "") or ""),
                "snapshot_key": str(row.get("snapshot_key", "") or ""),
                "total_ms": _safe_float(row.get("total_ms", metrics_map.get("total", 0.0))),
                "total_budget_ms": _safe_float(
                    row.get("total_budget_ms", budgets_map.get("total", 0.0))
                ),
                "overrun_count": int(_safe_float(overrun_count_raw)),
                "overruns": ", ".join(overrun_list) if overrun_list else "—",
                "blocks": ", ".join(blocks),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "captured_at_utc",
                "view",
                "snapshot_key",
                "total_ms",
                "total_budget_ms",
                "overrun_count",
                "overruns",
                "blocks",
            ]
        )
    hist = pd.DataFrame(rows)
    hist["captured_dt"] = pd.to_datetime(hist["captured_at_utc"], errors="coerce", utc=True)
    hist = hist.sort_values("captured_dt", ascending=False).reset_index(drop=True)
    return hist


def _render_perf_hero(*, history_df: pd.DataFrame, snapshot_count: int) -> None:
    total_events = int(len(history_df))
    if history_df.empty:
        latest_txt = "Sin muestras"
        p95_total = 0.0
        avg_total = 0.0
        overrun_events = 0
    else:
        latest_txt = str(history_df.iloc[0].get("captured_at_utc", "") or "Sin marca temporal")
        totals = pd.to_numeric(history_df["total_ms"], errors="coerce").fillna(0.0)
        p95_total = float(totals.quantile(0.95)) if not totals.empty else 0.0
        avg_total = float(totals.mean()) if not totals.empty else 0.0
        overrun_events = int(
            (pd.to_numeric(history_df["overrun_count"], errors="coerce").fillna(0) > 0).sum()
        )

    st.markdown(
        (
            '<div class="cfg-perf-hero">'
            '<div class="cfg-perf-title">Performance observability</div>'
            '<div class="cfg-perf-subtitle">'
            "Telemetría técnica centralizada. El Resumen queda limpio para usuario final."
            "</div>"
            '<div class="cfg-perf-kpi-grid">'
            f'<div class="cfg-perf-kpi"><span>Muestras</span><strong>{total_events}</strong></div>'
            f'<div class="cfg-perf-kpi"><span>Snapshots activos</span><strong>{snapshot_count}</strong></div>'
            f'<div class="cfg-perf-kpi"><span>P95 total</span><strong>{_fmt_ms(p95_total)}</strong></div>'
            f'<div class="cfg-perf-kpi"><span>Media total</span><strong>{_fmt_ms(avg_total)}</strong></div>'
            f'<div class="cfg-perf-kpi"><span>Eventos con overrun</span><strong>{overrun_events}</strong></div>'
            f'<div class="cfg-perf-kpi"><span>Última captura</span><strong>{escape(latest_txt)}</strong></div>'
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_performance_tab(*, settings: Settings) -> None:
    del settings  # sección operativa: usa telemetría en sesión, no configuración persistida.
    st.markdown("### Performance")
    st.caption("Panel técnico con histórico de tiempos y verificación de budget por bloque.")
    _inject_performance_zone_css()

    snapshots = list_perf_snapshots()
    history_df = _build_perf_history_df()
    _render_perf_hero(history_df=history_df, snapshot_count=len(snapshots))

    action_col, _ = st.columns([1.5, 4.0])
    with action_col:
        if st.button(
            "Limpiar histórico de performance",
            key="cfg_perf_clear_btn",
            width="stretch",
        ):
            removed = clear_perf_history()
            st.session_state["__cfg_flash_success"] = (
                f"Histórico de performance limpiado ({int(removed)} registro(s))."
            )
            st.session_state["__cfg_active_tab"] = "Performance"
            st.rerun()

    if snapshots:
        latest_rows: List[Dict[str, Any]] = []
        for snapshot_key, payload in snapshots.items():
            metrics = payload.get("metrics_ms")
            budgets = payload.get("budget_ms")
            metrics_map = metrics if isinstance(metrics, dict) else {}
            budgets_map = budgets if isinstance(budgets, dict) else {}
            overruns = payload.get("overruns")
            overrun_list = _as_non_empty_text_list(overruns)
            latest_rows.append(
                {
                    "snapshot_key": str(snapshot_key),
                    "view": str(payload.get("view", "") or ""),
                    "captured_at_utc": str(payload.get("captured_at_utc", "") or "—"),
                    "total_ms": _safe_float(metrics_map.get("total", 0.0)),
                    "total_budget_ms": _safe_float(budgets_map.get("total", 0.0)),
                    "overrun_count": int(len(overrun_list)),
                    "overruns": ", ".join(overrun_list) if overrun_list else "—",
                }
            )
        latest_df = (
            pd.DataFrame(latest_rows).sort_values(["view", "snapshot_key"]).reset_index(drop=True)
        )
        cards_html = ['<div class="cfg-perf-view-grid">']
        for row in latest_df.to_dict(orient="records"):
            is_warn = int(row.get("overrun_count", 0) or 0) > 0
            ratio = 0.0
            total_budget = _safe_float(row.get("total_budget_ms", 0.0))
            if total_budget > 0:
                ratio = (_safe_float(row.get("total_ms", 0.0)) / total_budget) * 100.0
            cards_html.append(
                f'<article class="cfg-perf-view-card {"is-warn" if is_warn else "is-ok"}">'
                '<div class="cfg-perf-view-head">'
                f'<span class="cfg-perf-view-name">{escape(str(row.get("view", "") or "-"))}</span>'
                f'<span class="cfg-perf-view-total">{_fmt_ms(row.get("total_ms", 0.0))}</span>'
                "</div>"
                f'<div class="cfg-perf-view-meta">Budget total: {_fmt_ms(total_budget)} '
                f"({ratio:.0f}% uso)</div>"
                f'<div class="cfg-perf-view-meta">Overruns: {escape(str(row.get("overruns", "—") or "—"))}</div>'
                f'<div class="cfg-perf-view-meta">{escape(str(row.get("captured_at_utc", "—") or "—"))}</div>'
                "</article>"
            )
        cards_html.append("</div>")
        st.markdown("#### Estado actual por vista")
        st.markdown("".join(cards_html), unsafe_allow_html=True)
    else:
        st.info("Todavía no hay snapshots de performance en esta sesión.")

    if not history_df.empty:
        st.markdown("#### Tendencia de tiempos (total)")
        trend = history_df.copy(deep=False)
        trend = trend.dropna(subset=["captured_dt"]).sort_values("captured_dt", ascending=True)
        fig = go.Figure()
        view_color_map = {
            "KPIs": BBVA_LIGHT.electric_blue,
            "Summary": BBVA_SIGNAL_ORANGE_1,
            "Overview": BBVA_LIGHT.core_blue,
            "Issues": BBVA_SIGNAL_RED_1,
            "Trends": BBVA_SIGNAL_GREEN_1,
            "default": BBVA_LIGHT.ink_muted,
        }
        for view_name in sorted(trend["view"].astype(str).unique().tolist()):
            sub = trend[trend["view"].astype(str) == view_name]
            if sub.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=sub["captured_dt"],
                    y=pd.to_numeric(sub["total_ms"], errors="coerce").fillna(0.0),
                    mode="lines+markers",
                    name=view_name,
                    line=dict(
                        width=2.2,
                        color=view_color_map.get(view_name, view_color_map["default"]),
                    ),
                    marker=dict(size=6),
                    hovertemplate=(
                        f"Vista: {escape(view_name)}<br>"
                        "Total: %{y:.0f} ms<br>"
                        "Fecha: %{x}<extra></extra>"
                    ),
                )
            )
        fig.update_layout(
            height=330,
            margin=dict(l=14, r=14, t=18, b=54),
            xaxis_title="Captura",
            yaxis_title="Tiempo total (ms)",
            legend_title_text="",
        )
        fig = apply_plotly_bbva(fig, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Registro de ejecución")
        history_view = history_df.loc[
            :,
            [
                "captured_at_utc",
                "view",
                "snapshot_key",
                "total_ms",
                "total_budget_ms",
                "overrun_count",
                "overruns",
                "blocks",
            ],
        ].copy(deep=False)
        st.dataframe(
            history_view,
            hide_index=True,
            width="stretch",
            column_config={
                "captured_at_utc": st.column_config.TextColumn("Captura (UTC)"),
                "view": st.column_config.TextColumn("Vista"),
                "snapshot_key": st.column_config.TextColumn("Snapshot key"),
                "total_ms": st.column_config.NumberColumn("Total (ms)", format="%.0f"),
                "total_budget_ms": st.column_config.NumberColumn("Budget (ms)", format="%.0f"),
                "overrun_count": st.column_config.NumberColumn("Overruns", format="%d"),
                "overruns": st.column_config.TextColumn("Bloques excedidos"),
                "blocks": st.column_config.TextColumn("Bloques medidos"),
            },
        )


def _render_selected_source_chips(
    selected_source_ids: List[str], source_label_by_id: Dict[str, str]
) -> None:
    if not selected_source_ids:
        return
    chips_html = ['<div class="cfg-delete-chip-wrap">']
    for sid in selected_source_ids:
        label = source_label_by_id.get(str(sid), str(sid))
        chips_html.append(
            '<span class="cfg-delete-chip"><span class="cfg-delete-chip-dot"></span>'
            f"{escape(label)}"
            "</span>"
        )
    chips_html.append("</div>")
    st.markdown("".join(chips_html), unsafe_allow_html=True)


def _render_source_delete_container(
    *,
    section_title: str,
    source_label: str,
    selected_source_ids: List[str],
    selected_label_by_id: Dict[str, str],
    key_prefix: str,
) -> Dict[str, Any]:
    st.markdown(
        f'<div class="bbva-icon-no-draw-title">{escape(section_title)}</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True, key=f"{key_prefix}_delete_shell"):
        st.markdown("#### Zona segura de eliminación")
        st.caption(
            "La eliminación se ejecuta al pulsar Guardar en esta pestaña. "
            "El saneado de cache asociado se aplica siempre."
        )

        has_selection = bool(selected_source_ids)
        if has_selection:
            plural = "s" if len(selected_source_ids) != 1 else ""
            st.markdown(
                f'<div class="cfg-delete-counter"><strong>{len(selected_source_ids)}</strong> '
                f"fuente{plural} seleccionada{plural} desde la tabla.</div>",
                unsafe_allow_html=True,
            )
            _render_selected_source_chips(selected_source_ids, selected_label_by_id)
        else:
            st.markdown(
                f'<div class="cfg-delete-ghost">Marca en la tabla las fuentes {source_label} '
                "que quieras eliminar. Aquí aparecerán como chips country · alias.</div>",
                unsafe_allow_html=True,
            )

        confirm_target = (
            f"estas fuentes {source_label}"
            if len(selected_source_ids) != 1
            else f"esta fuente {source_label}"
        )
        confirm = st.checkbox(
            f"Confirmo que quiero eliminar {confirm_target} de forma permanente.",
            key=f"{key_prefix}_delete_confirm",
        )
        phrase = st.text_input(
            "Escribe ELIMINAR para confirmar",
            value="",
            key=f"{key_prefix}_delete_phrase",
            help="Confirmación reforzada para evitar borrados accidentales.",
        )

        phrase_ok = _is_delete_phrase_valid(phrase)
        has_partial_input = bool(has_selection or confirm or str(phrase).strip())
        armed = bool(has_selection and confirm and phrase_ok)
        valid = bool((not has_partial_input) or armed)

        if has_partial_input and not has_selection:
            st.warning(f"Selecciona al menos una fuente {source_label} para eliminar.")
        elif has_partial_input and not armed:
            st.warning(
                "Para aplicar la eliminación debes seleccionar fuentes, "
                "marcar confirmación y escribir ELIMINAR."
            )
        elif armed:
            st.success(
                f"Eliminación preparada ({len(selected_source_ids)}). "
                "Se aplicará al guardar configuración."
            )

        return {"source_ids": selected_source_ids, "armed": armed, "valid": valid}


def _rows_from_cache_inventory(settings: Settings) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in cache_inventory(settings):
        rows.append(
            {
                "__reset__": False,
                "__cache_id__": _as_str(row.get("cache_id")),
                "cache": _as_str(row.get("label")),
                "registros": int(row.get("records", 0) or 0),
                "ruta": _as_str(row.get("path")),
            }
        )
    return rows


def _selected_caches_from_editor(df: pd.DataFrame) -> Tuple[List[str], Dict[str, str]]:
    selected_ids: List[str] = []
    label_by_id: Dict[str, str] = {}

    for row in df.to_dict(orient="records"):
        if not _boolish(row.get("__reset__"), default=False):
            continue
        cache_id = _as_str(row.get("__cache_id__"))
        label = _as_str(row.get("cache")) or cache_id
        if not cache_id:
            continue
        if cache_id not in selected_ids:
            selected_ids.append(cache_id)
            label_by_id[cache_id] = label
    return selected_ids, label_by_id


def _render_cache_reset_container(
    *,
    selected_cache_ids: List[str],
    selected_label_by_id: Dict[str, str],
    key_prefix: str,
) -> Dict[str, Any]:
    st.markdown(
        '<div class="bbva-icon-recycle-title">Resetear caché</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True, key=f"{key_prefix}_cache_reset_shell"):
        st.markdown("#### Zona segura de reseteo")
        st.caption(
            "La operación es inmediata y vacía el contenido del cache seleccionado "
            "(deja 0 registros). No requiere Guardar configuración."
        )

        has_selection = bool(selected_cache_ids)
        if has_selection:
            plural = "s" if len(selected_cache_ids) != 1 else ""
            st.markdown(
                f'<div class="cfg-delete-counter"><strong>{len(selected_cache_ids)}</strong> '
                f"cache{plural} seleccionado{plural}.</div>",
                unsafe_allow_html=True,
            )
            _render_selected_source_chips(selected_cache_ids, selected_label_by_id)
        else:
            st.markdown(
                '<div class="cfg-delete-ghost">Marca en la tabla los caches que quieras resetear. '
                "Aquí aparecerán como chips.</div>",
                unsafe_allow_html=True,
            )

        confirm = st.checkbox(
            "Confirmo que quiero resetear los caches seleccionados.",
            key=f"{key_prefix}_cache_reset_confirm",
        )
        phrase = st.text_input(
            "Escribe RESETEAR para confirmar",
            value="",
            key=f"{key_prefix}_cache_reset_phrase",
            help="Confirmación reforzada para evitar resets accidentales.",
        )
        phrase_ok = _is_reset_phrase_valid(phrase)
        has_partial_input = bool(has_selection or confirm or str(phrase).strip())
        armed = bool(has_selection and confirm and phrase_ok)
        valid = bool((not has_partial_input) or armed)

        if has_partial_input and not has_selection:
            st.warning("Selecciona al menos un cache para resetear.")
        elif has_partial_input and not armed:
            st.warning(
                "Para aplicar el reseteo debes seleccionar caches, "
                "marcar confirmación y escribir RESETEAR."
            )
        elif armed:
            st.success(
                f"Reseteo preparado ({len(selected_cache_ids)}). "
                "Pulsa el botón para vaciar los registros."
            )

        return {"cache_ids": selected_cache_ids, "armed": armed, "valid": valid}


def _render_full_restore_container(*, key_prefix: str) -> Dict[str, Any]:
    st.markdown(
        '<div class="bbva-icon-recycle-title">Restaurar configuración completa</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True, key=f"{key_prefix}_restore_shell"):
        st.markdown("#### Zona segura de restauración")

        confirm = st.checkbox(
            "Confirmo que quiero restaurar toda la configuración desde cero.",
            key=f"{key_prefix}_restore_confirm",
        )
        phrase = st.text_input(
            "Escribe RESTAURAR para confirmar",
            value="",
            key=f"{key_prefix}_restore_phrase",
            help="Confirmación reforzada para evitar restauraciones accidentales.",
        )

        phrase_ok = _is_restore_phrase_valid(phrase)
        has_partial_input = bool(confirm or str(phrase).strip())
        armed = bool(confirm and phrase_ok)
        valid = bool((not has_partial_input) or armed)

        if has_partial_input and not armed:
            st.warning(
                "Para restaurar la configuración debes marcar confirmación y escribir RESTAURAR."
            )
        elif armed:
            st.success("Restauración preparada. Pulsa el botón para aplicarla ahora.")

        return {"armed": armed, "valid": valid}


def _render_cache_reset_results(results: List[Dict[str, Any]]) -> None:
    if not results:
        return
    for row in results:
        label = str(row.get("label") or row.get("cache_id") or "cache")
        before = int(row.get("before", 0) or 0)
        after = int(row.get("after", 0) or 0)
        reset = int(row.get("reset", 0) or 0)
        st.info(f"{label}: {before} -> {after} registros (reseteados {reset}).")


def _rows_from_jira_settings(settings: Settings, countries: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for src in jira_sources(settings):
        country = _as_str(src.get("country"))
        if country not in countries:
            continue
        rows.append(
            {
                "__delete__": False,
                "__source_id__": _as_str(src.get("source_id")),
                "country": country,
                "alias": _as_str(src.get("alias")),
                "jql": _as_str(src.get("jql")),
            }
        )
    return rows


def _rows_from_helix_settings(settings: Settings, countries: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for src in helix_sources(settings):
        country = _as_str(src.get("country"))
        if country not in countries:
            continue
        rows.append(
            {
                "__delete__": False,
                "__source_id__": _as_str(src.get("source_id")),
                "country": country,
                "alias": _as_str(src.get("alias")),
                "service_origin_buug": _as_str(src.get("service_origin_buug")),
                "service_origin_n1": _as_str(src.get("service_origin_n1")),
                "service_origin_n2": _as_str(src.get("service_origin_n2")),
            }
        )
    return rows


def _normalize_jira_rows(
    df: pd.DataFrame, countries: List[str]
) -> Tuple[List[Dict[str, str]], List[str]]:
    out: List[Dict[str, str]] = []
    errors: List[str] = []
    seen: set[tuple[str, str]] = set()

    for idx, row in enumerate(df.to_dict(orient="records"), start=1):
        if _boolish(row.get("__delete__"), default=False):
            continue
        country = _as_str(row.get("country"))
        alias = _as_str(row.get("alias"))
        jql = _as_str(row.get("jql"))

        if not country and not alias and not jql:
            continue
        if country not in countries:
            errors.append(f"Jira fila {idx}: país inválido.")
            continue
        if not alias:
            errors.append(f"Jira fila {idx}: alias obligatorio.")
            continue
        if not jql:
            errors.append(f"Jira fila {idx}: JQL obligatorio.")
            continue

        dedup_key = (country, alias.lower())
        if dedup_key in seen:
            errors.append(f"Jira fila {idx}: alias duplicado para {country}.")
            continue
        seen.add(dedup_key)
        out.append({"country": country, "alias": alias, "jql": jql})

    return out, errors


def _normalize_helix_rows(
    df: pd.DataFrame, countries: List[str]
) -> Tuple[List[Dict[str, str]], List[str]]:
    out: List[Dict[str, str]] = []
    errors: List[str] = []
    seen: set[tuple[str, str]] = set()

    for idx, row in enumerate(df.to_dict(orient="records"), start=1):
        if _boolish(row.get("__delete__"), default=False):
            continue
        country = _as_str(row.get("country"))
        alias = _as_str(row.get("alias"))
        service_origin_buug = _as_str(row.get("service_origin_buug"))
        service_origin_n1 = _as_str(row.get("service_origin_n1"))
        service_origin_n2 = _as_str(row.get("service_origin_n2"))

        if not any(
            [
                country,
                alias,
                service_origin_buug,
                service_origin_n1,
                service_origin_n2,
            ]
        ):
            continue
        if country not in countries:
            errors.append(f"Helix fila {idx}: país inválido.")
            continue
        if not alias:
            errors.append(f"Helix fila {idx}: alias obligatorio.")
            continue

        dedup_key = (country, alias.lower())
        if dedup_key in seen:
            errors.append(f"Helix fila {idx}: alias duplicado para {country}.")
            continue
        seen.add(dedup_key)
        payload = {
            "country": country,
            "alias": alias,
        }
        if service_origin_buug:
            payload["service_origin_buug"] = service_origin_buug
        if service_origin_n1:
            payload["service_origin_n1"] = service_origin_n1
        if service_origin_n2:
            payload["service_origin_n2"] = service_origin_n2
        out.append(payload)

    return out, errors


def _selected_sources_from_editor(
    df: pd.DataFrame, *, source_type: str
) -> Tuple[List[str], Dict[str, str]]:
    selected_ids: List[str] = []
    label_by_id: Dict[str, str] = {}

    for idx, row in enumerate(df.to_dict(orient="records"), start=1):
        if not _boolish(row.get("__delete__"), default=False):
            continue
        country = _as_str(row.get("country"))
        alias = _as_str(row.get("alias"))
        sid = _as_str(row.get("__source_id__"))
        if not sid and country and alias:
            sid = build_source_id(source_type, country, alias)
        token = sid or f"{_DELETE_ROW_TOKEN_PREFIX}{source_type}:{idx}"
        if token not in selected_ids:
            selected_ids.append(token)
            label_by_id[token] = f"{country or 'N/A'} · {alias or 'Sin alias'}"

    return selected_ids, label_by_id


def _source_ids_for_cache_purge(selected_ids: List[str]) -> List[str]:
    out: List[str] = []
    for value in selected_ids:
        sid = _as_str(value)
        if not sid or sid.startswith(_DELETE_ROW_TOKEN_PREFIX):
            continue
        if sid not in out:
            out.append(sid)
    return out


def _clear_jira_delete_widget_state() -> None:
    _queue_widget_state_clear(
        [
            "cfg_jira_delete_confirm",
            "cfg_jira_delete_phrase",
            "cfg_jira_sources_editor",
            "cfg_jira_sources_rows_state",
        ]
    )


def _clear_helix_delete_widget_state() -> None:
    _queue_widget_state_clear(
        [
            "cfg_helix_delete_confirm",
            "cfg_helix_delete_phrase",
            "cfg_helix_sources_editor",
            "cfg_helix_sources_rows_state",
        ]
    )


def _clear_cache_reset_widget_state() -> None:
    _queue_widget_state_clear(
        [
            "cfg_cache_reset_editor",
            "cfg_cache_cache_reset_confirm",
            "cfg_cache_cache_reset_phrase",
        ]
    )


def _clear_restore_widget_state() -> None:
    _queue_widget_state_clear(
        [
            "cfg_prefs_restore_confirm",
            "cfg_prefs_restore_phrase",
        ]
    )


def _queue_all_config_widget_state_clear() -> None:
    keys = [str(k).strip() for k in st.session_state.keys() if str(k).strip().startswith("cfg_")]
    _queue_widget_state_clear(keys)


def _queue_widget_state_clear(keys: List[str]) -> None:
    pending = st.session_state.get("__cfg_pending_widget_clears", [])
    if not isinstance(pending, list):
        pending = []
    merged = [str(k).strip() for k in pending if str(k).strip()]
    for key in keys:
        k = str(key or "").strip()
        if k and k not in merged:
            merged.append(k)
    st.session_state["__cfg_pending_widget_clears"] = merged


def _apply_queued_widget_state_clear() -> None:
    pending = st.session_state.pop("__cfg_pending_widget_clears", [])
    if not isinstance(pending, list):
        return
    for key in pending:
        k = str(key or "").strip()
        if k:
            st.session_state.pop(k, None)


def _clear_runtime_state_after_restore() -> None:
    # Theme + scope + filters are hydrated once; clear them so next run reflects restored settings.
    for key in [
        "workspace_dark_mode",
        "workspace_country",
        "workspace_scope_mode",
        "workspace_source_id",
        "workspace_source_id_aux",
        "filter_status",
        "filter_priority",
        "filter_assignee",
        "__filters_bootstrapped_from_env",
        "__cfg_cache_reset_results",
    ]:
        st.session_state.pop(key, None)


def _apply_workspace_scope(df: pd.DataFrame, *, settings: Settings) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    selected_country = str(st.session_state.get("workspace_country") or "").strip()
    selected_source_id = str(st.session_state.get("workspace_source_id") or "").strip()
    scope_mode = str(st.session_state.get("workspace_scope_mode") or "source").strip().lower()
    if scope_mode not in {"country", "source"}:
        scope_mode = "source"
    if not selected_country and not selected_source_id:
        return df.copy(deep=False)

    mask = pd.Series(True, index=df.index)
    if selected_country and "country" in df.columns:
        mask &= df["country"].fillna("").astype(str).eq(selected_country)
    if "source_id" in df.columns:
        if scope_mode == "source":
            if selected_source_id:
                mask &= df["source_id"].fillna("").astype(str).eq(selected_source_id)
        else:
            available_source_ids = (
                df.loc[
                    df["country"].fillna("").astype(str).eq(selected_country),
                    "source_id",
                ]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            available_source_ids = sorted({sid for sid in available_source_ids.tolist() if sid})
            selected_rollup = rollup_source_ids(
                settings,
                country=selected_country,
                available_source_ids=available_source_ids,
            )
            if selected_rollup:
                mask &= df["source_id"].fillna("").astype(str).isin(selected_rollup)
    return df.loc[mask].copy(deep=False)


def _analysis_window_defaults(settings: Settings) -> Tuple[int, int]:
    configured_months = normalize_analysis_lookback_months(
        getattr(settings, "ANALYSIS_LOOKBACK_MONTHS", 12),
        default=12,
    )
    try:
        df_all = load_issues_df(settings.DATA_PATH)
    except Exception:
        max_months = max(12, configured_months)
        return max_months, configured_months

    if df_all.empty:
        max_months = max(12, configured_months)
        return max_months, configured_months

    scoped_df = _apply_workspace_scope(df_all, settings=settings)
    base_df = scoped_df if not scoped_df.empty else df_all
    available_months = int(max_available_backlog_months(base_df))
    parsed_months = int(parse_analysis_lookback_months(settings))
    current_months = max(1, parsed_months)
    max_months = max(12, available_months, current_months)
    return max_months, current_months


def _analysis_month_steps(max_months: int) -> List[int]:
    target = max(1, int(max_months))
    base_steps = [1, 2, 3, 4, 6, 9, 12, 18, 24, 36, 48, 60]
    options = sorted({m for m in base_steps if m <= target} | {target})
    return options or [1]


def _nearest_option(value: int, *, options: List[int]) -> int:
    if not options:
        return max(1, int(value))
    tgt = max(1, int(value))
    return min(options, key=lambda opt: abs(int(opt) - tgt))


def _rollup_sources_to_env_json(selection_by_country: Dict[str, List[str]]) -> str:
    rows: List[Dict[str, Any]] = []
    for country in sorted(selection_by_country.keys()):
        source_ids = [
            str(sid).strip()
            for sid in list(selection_by_country.get(country, []) or [])
            if str(sid).strip()
        ]
        if not source_ids:
            continue
        rows.append({"country": country, "source_ids": source_ids})
    return cast(str, to_env_json(rows))


def render(settings: Settings) -> None:
    _apply_queued_widget_state_clear()
    flash_success = str(st.session_state.pop("__cfg_flash_success", "") or "").strip()
    if flash_success:
        st.success(flash_success)

    countries = supported_countries(settings)
    jira_delete_cfg: Dict[str, Any] = {"source_ids": [], "armed": False, "valid": True}
    helix_delete_cfg: Dict[str, Any] = {"source_ids": [], "armed": False, "valid": True}
    analysis_max_months = 1
    analysis_selected_months = 1
    _inject_delete_zone_css()
    _inject_preferences_zone_css()

    st.subheader("Configuración")

    # Avoid emoji icons in tab labels: some environments render them as empty squares.
    tab_labels = ["Preferencias", "Jira", "Helix", "Agregados", "Cache", "Performance"]
    active_tab = str(st.session_state.get("__cfg_active_tab", "Preferencias") or "").strip()
    if active_tab not in tab_labels:
        active_tab = "Preferencias"
    st.session_state["__cfg_active_tab"] = active_tab
    with st.container(key="cfg_tabs_shell"):
        t_prefs, t_jira, t_helix, t_agg, t_caches, t_perf = st.tabs(tab_labels, default=active_tab)

    with t_jira:
        st.markdown("### Jira global")

        c1, c2 = st.columns(2)
        with c1:
            jira_base = st.text_input(
                "Jira Base URL (global)",
                value=settings.JIRA_BASE_URL,
                key="cfg_jira_base",
            )
        with c2:
            jira_browser = st.selectbox(
                "Navegador Jira (lectura cookie, global)",
                options=["chrome", "edge"],
                index=0 if settings.JIRA_BROWSER == "chrome" else 1,
                key="cfg_jira_browser",
            )

        st.markdown("### Fuentes Jira por país")
        st.caption("Alias y JQL son obligatorios.")
        jira_rows = _rows_from_jira_settings(settings, countries)
        jira_default_row = {
            "__delete__": False,
            "__source_id__": "",
            "country": countries[0] if countries else "",
            "alias": "",
            "jql": "",
        }
        jira_rows_state_key = "cfg_jira_sources_rows_state"
        if jira_rows_state_key not in st.session_state:
            st.session_state[jira_rows_state_key] = jira_rows or [jira_default_row]
        if st.button("Añadir fila", key="cfg_jira_add_row_btn", width="stretch"):
            raw_rows = st.session_state.get(jira_rows_state_key, [])
            rows_state = [dict(x) for x in raw_rows] if isinstance(raw_rows, list) else []
            rows_state.append(dict(jira_default_row))
            st.session_state[jira_rows_state_key] = rows_state
        jira_rows_for_editor = st.session_state.get(
            jira_rows_state_key, jira_rows or [jira_default_row]
        )
        jira_df = pd.DataFrame(jira_rows_for_editor)
        jira_editor = st.data_editor(
            jira_df,
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            key="cfg_jira_sources_editor",
            column_order=["__delete__", "country", "alias", "jql"],
            column_config={
                "__delete__": st.column_config.CheckboxColumn("Eliminar"),
                "country": st.column_config.SelectboxColumn("country", options=countries),
                "alias": st.column_config.TextColumn("alias"),
                "jql": st.column_config.TextColumn("jql"),
            },
        )
        st.session_state[jira_rows_state_key] = jira_editor.to_dict(orient="records")
        _render_sources_excel_download(
            jira_editor,
            source_type="jira",
            key="cfg_export_jira_sources_xlsx",
            filename_prefix="fuentes_jira",
            sheet_name="Fuentes Jira",
        )

        jira_delete_ids, jira_delete_labels = _selected_sources_from_editor(
            jira_editor, source_type="jira"
        )
        jira_delete_cfg = _render_source_delete_container(
            section_title="Eliminar fuente Jira",
            source_label="Jira",
            selected_source_ids=jira_delete_ids,
            selected_label_by_id=jira_delete_labels,
            key_prefix="cfg_jira",
        )

        jira_save_help = None
        if not bool(jira_delete_cfg.get("valid", True)):
            jira_save_help = (
                "Completa la confirmación de eliminación (checkbox + texto ELIMINAR) "
                "o limpia esos campos para continuar."
            )
        if st.button(
            "Guardar configuración",
            key="cfg_save_jira_btn",
            disabled=not bool(jira_delete_cfg.get("valid", True)),
            help=jira_save_help,
        ):
            jira_clean, jira_errors = _normalize_jira_rows(jira_editor, countries)
            if jira_errors:
                for err in jira_errors:
                    st.error(err)
                return

            new_settings = _safe_update_settings(
                settings,
                {
                    "JIRA_BASE_URL": str(jira_base).strip(),
                    "JIRA_BROWSER": str(jira_browser).strip(),
                    "JIRA_SOURCES_JSON": to_env_json(jira_clean),
                },
            )
            _save_settings_with_migrations(new_settings)

            any_deletion = False
            if bool(jira_delete_cfg.get("armed", False)):
                jira_delete_tokens = [
                    str(x).strip() for x in jira_delete_cfg.get("source_ids", []) if str(x).strip()
                ]
                if jira_delete_tokens:
                    any_deletion = True
                    jira_delete_sids = _source_ids_for_cache_purge(jira_delete_tokens)
                    jira_purge_total = {
                        "issues_removed": 0,
                        "helix_items_removed": 0,
                        "learning_scopes_removed": 0,
                    }
                    for delete_sid in jira_delete_sids:
                        purge_stats = purge_source_cache(new_settings, delete_sid)
                        jira_purge_total = _merge_purge_stats(jira_purge_total, purge_stats)
                    st.success(f"Fuentes Jira eliminadas: {len(jira_delete_tokens)}.")
                    if jira_delete_sids:
                        _render_purge_stats(jira_purge_total)
                    if len(jira_delete_sids) != len(jira_delete_tokens):
                        st.info(
                            "Algunas fuentes no tenían source_id resoluble; "
                            "se eliminó la configuración pero no había cache asociado que sanear."
                        )

            if any_deletion:
                _clear_jira_delete_widget_state()
                st.session_state["__cfg_flash_success"] = (
                    "Configuración Jira y eliminación aplicadas."
                )
            else:
                _queue_widget_state_clear(
                    [
                        "cfg_jira_delete_confirm",
                        "cfg_jira_delete_phrase",
                        "cfg_jira_sources_rows_state",
                    ]
                )
                st.session_state["__cfg_flash_success"] = "Configuración Jira guardada."
            st.session_state["__cfg_active_tab"] = "Jira"
            st.rerun()

    with t_helix:
        st.markdown("### Helix")
        st.caption("Configuración común de conexión y autenticación para todas las fuentes Helix.")

        h1, h2, h3 = st.columns([1.2, 1.0, 1.0])
        with h1:
            helix_default_proxy = st.text_input(
                "Proxy",
                value=_as_str(getattr(settings, "HELIX_PROXY", "")),
                key="cfg_helix_proxy_default",
                placeholder="http://127.0.0.1:8999",
            )
        with h2:
            helix_default_browser = st.selectbox(
                "Browser",
                options=["chrome", "edge"],
                index=0 if _as_str(settings.HELIX_BROWSER) == "chrome" else 1,
                key="cfg_helix_browser_default",
            )
        with h3:
            helix_default_ssl_verify = st.selectbox(
                "SSL verify",
                options=["true", "false"],
                index=(
                    0 if _boolish(getattr(settings, "HELIX_SSL_VERIFY", True), default=True) else 1
                ),
                key="cfg_helix_ssl_default",
            )

        helix_dashboard_url = st.text_input(
            "Helix Dashboard URL",
            value=_as_str(
                getattr(
                    settings,
                    "HELIX_DASHBOARD_URL",
                    "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
                )
            ),
            key="cfg_helix_dashboard_url",
        )
        st.caption("Modo de ingesta Helix: ARSQL (único modo soportado).")

        st.markdown("### Fuentes Helix por país")
        st.caption("Alias y filtros de servicio por fuente. La conexión Helix se define arriba.")
        helix_rows = _rows_from_helix_settings(settings, countries)
        helix_default_row = {
            "__delete__": False,
            "__source_id__": "",
            "country": countries[0] if countries else "",
            "alias": "",
            "service_origin_buug": "BBVA México",
            "service_origin_n1": "ENTERPRISE WEB",
            "service_origin_n2": "",
        }
        helix_rows_state_key = "cfg_helix_sources_rows_state"
        if helix_rows_state_key not in st.session_state:
            st.session_state[helix_rows_state_key] = helix_rows or [helix_default_row]
        if st.button("Añadir fila", key="cfg_helix_add_row_btn", width="stretch"):
            raw_rows = st.session_state.get(helix_rows_state_key, [])
            rows_state = [dict(x) for x in raw_rows] if isinstance(raw_rows, list) else []
            rows_state.append(dict(helix_default_row))
            st.session_state[helix_rows_state_key] = rows_state
        helix_rows_for_editor = st.session_state.get(
            helix_rows_state_key, helix_rows or [helix_default_row]
        )
        helix_df = pd.DataFrame(helix_rows_for_editor)
        helix_editor = st.data_editor(
            helix_df,
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            key="cfg_helix_sources_editor",
            column_order=[
                "__delete__",
                "country",
                "alias",
                "service_origin_buug",
                "service_origin_n1",
                "service_origin_n2",
            ],
            column_config={
                "__delete__": st.column_config.CheckboxColumn("Eliminar"),
                "country": st.column_config.SelectboxColumn("country", options=countries),
                "alias": st.column_config.TextColumn("alias"),
                "service_origin_buug": st.column_config.TextColumn("Servicio Origen BU/UG"),
                "service_origin_n1": st.column_config.TextColumn("Servicio Origen N1 (CSV)"),
                "service_origin_n2": st.column_config.TextColumn("Servicio Origen N2 (CSV)"),
            },
        )
        st.session_state[helix_rows_state_key] = helix_editor.to_dict(orient="records")
        _render_sources_excel_download(
            helix_editor,
            source_type="helix",
            key="cfg_export_helix_sources_xlsx",
            filename_prefix="fuentes_helix",
            sheet_name="Fuentes Helix",
        )

        helix_delete_ids, helix_delete_labels = _selected_sources_from_editor(
            helix_editor, source_type="helix"
        )
        helix_delete_cfg = _render_source_delete_container(
            section_title="Eliminar fuente Helix",
            source_label="Helix",
            selected_source_ids=helix_delete_ids,
            selected_label_by_id=helix_delete_labels,
            key_prefix="cfg_helix",
        )

        helix_save_help = None
        if not bool(helix_delete_cfg.get("valid", True)):
            helix_save_help = (
                "Completa la confirmación de eliminación (checkbox + texto ELIMINAR) "
                "o limpia esos campos para continuar."
            )
        if st.button(
            "Guardar configuración",
            key="cfg_save_helix_btn",
            disabled=not bool(helix_delete_cfg.get("valid", True)),
            help=helix_save_help,
        ):
            helix_clean, helix_errors = _normalize_helix_rows(helix_editor, countries)
            if helix_errors:
                for err in helix_errors:
                    st.error(err)
                return
            new_settings = _safe_update_settings(
                settings,
                {
                    "HELIX_SOURCES_JSON": to_env_json(helix_clean),
                    "HELIX_BROWSER": str(helix_default_browser).strip(),
                    "HELIX_PROXY": str(helix_default_proxy).strip(),
                    "HELIX_SSL_VERIFY": str(helix_default_ssl_verify).strip().lower(),
                    "HELIX_DASHBOARD_URL": str(helix_dashboard_url).strip(),
                },
            )
            _save_settings_with_migrations(new_settings)

            any_deletion = False
            if bool(helix_delete_cfg.get("armed", False)):
                helix_delete_tokens = [
                    str(x).strip() for x in helix_delete_cfg.get("source_ids", []) if str(x).strip()
                ]
                if helix_delete_tokens:
                    any_deletion = True
                    helix_delete_sids = _source_ids_for_cache_purge(helix_delete_tokens)
                    helix_purge_total = {
                        "issues_removed": 0,
                        "helix_items_removed": 0,
                        "learning_scopes_removed": 0,
                    }
                    for delete_sid in helix_delete_sids:
                        purge_stats = purge_source_cache(new_settings, delete_sid)
                        helix_purge_total = _merge_purge_stats(helix_purge_total, purge_stats)
                    st.success(f"Fuentes Helix eliminadas: {len(helix_delete_tokens)}.")
                    if helix_delete_sids:
                        _render_purge_stats(helix_purge_total)
                    if len(helix_delete_sids) != len(helix_delete_tokens):
                        st.info(
                            "Algunas fuentes no tenían source_id resoluble; "
                            "se eliminó la configuración pero no había cache asociado que sanear."
                        )

            if any_deletion:
                _clear_helix_delete_widget_state()
                st.session_state["__cfg_flash_success"] = (
                    "Configuración Helix y eliminación aplicadas."
                )
            else:
                _queue_widget_state_clear(
                    [
                        "cfg_helix_delete_confirm",
                        "cfg_helix_delete_phrase",
                        "cfg_helix_sources_rows_state",
                    ]
                )
                st.session_state["__cfg_flash_success"] = "Configuración Helix guardada."
            st.session_state["__cfg_active_tab"] = "Helix"
            st.rerun()

    with t_prefs:
        with st.container(key="cfg_prefs_shell"):
            st.markdown("### Preferencias")
            stored_theme_pref = str(getattr(settings, "THEME", "auto") or "auto").strip().lower()
            if stored_theme_pref in {"dark", "light"}:
                theme_default = stored_theme_pref
            else:
                theme_default = (
                    "dark" if bool(st.session_state.get("workspace_dark_mode", False)) else "light"
                )

            with st.container(border=True, key="cfg_prefs_card_workspace"):
                st.markdown("#### Ambiente de trabajo")
                theme_mode = st.radio(
                    "Modo visual",
                    options=["light", "dark"],
                    index=0 if theme_default == "light" else 1,
                    format_func=lambda v: "Claro" if v == "light" else "Oscuro",
                    horizontal=True,
                    key="cfg_workspace_theme_mode",
                )
                st.caption("Se guarda como preferencia del usuario.")

            with st.container(border=True, key="cfg_prefs_card_analysis"):
                st.markdown("#### Profundidad del análisis")
                analysis_max_months, analysis_selected_months = _analysis_window_defaults(settings)
                month_options = _analysis_month_steps(analysis_max_months)
                if len(month_options) <= 1:
                    only_month = int(month_options[0]) if month_options else 1
                    analysis_selected_months = only_month
                    st.session_state["cfg_analysis_depth_months"] = only_month
                    st.selectbox(
                        "Meses analizados en backlog",
                        options=[only_month],
                        index=0,
                        key="cfg_analysis_depth_months_single",
                        disabled=True,
                        format_func=lambda m: f"{int(m)} mes" if int(m) == 1 else f"{int(m)} meses",
                        help=(
                            "Se habilita automáticamente cuando exista histórico suficiente "
                            "en la caché de incidencias."
                        ),
                    )
                else:
                    st.session_state.pop("cfg_analysis_depth_months_single", None)
                    selected_months = st.select_slider(
                        "Meses analizados en backlog",
                        options=month_options,
                        value=_nearest_option(analysis_selected_months, options=month_options),
                        key="cfg_analysis_depth_months",
                        format_func=lambda m: f"{int(m)} mes" if int(m) == 1 else f"{int(m)} meses",
                        help="Filtro global aplicado en dashboard, insights e informe PPT.",
                    )
                    analysis_selected_months = int(
                        selected_months[0]
                        if isinstance(selected_months, tuple)
                        else selected_months
                    )
                st.caption(
                    f"Estado: últimos {int(analysis_selected_months)} "
                    f"{'mes' if int(analysis_selected_months) == 1 else 'meses'}."
                )

            with st.container(border=True, key="cfg_prefs_card_quincena"):
                st.markdown("#### Alcance quincenal")
                quincena_last_finished_default = _boolish(
                    getattr(settings, "QUINCENA_LAST_FINISHED_ONLY", "false"),
                    default=False,
                )
                st.session_state.setdefault(
                    "cfg_quincena_last_finished_only",
                    quincena_last_finished_default,
                )
                quincena_last_finished_only = st.checkbox(
                    "Usar última quincena finalizada",
                    key="cfg_quincena_last_finished_only",
                    help=(
                        "Desmarcado: usa la quincena natural en curso (1-15 o 16-fin de mes). "
                        "Marcado: usa siempre la última quincena ya cerrada."
                    ),
                )
                st.caption(
                    "Aplicación transversal en Insights, filtros quincenales y "
                    "reportes de seguimiento."
                )

            with st.container(border=True, key="cfg_prefs_card_open_focus"):
                st.markdown("#### Criterio de foco en abiertas")
                open_focus_mode_default = normalize_open_issues_focus_mode(
                    getattr(
                        settings, "OPEN_ISSUES_FOCUS_MODE", OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH
                    )
                )
                st.session_state.setdefault("cfg_open_issues_focus_mode", open_focus_mode_default)
                if str(st.session_state.get("cfg_open_issues_focus_mode") or "").strip() not in {
                    OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH,
                    OPEN_ISSUES_FOCUS_MODE_MAESTRAS,
                }:
                    st.session_state["cfg_open_issues_focus_mode"] = open_focus_mode_default
                open_issues_focus_mode = st.radio(
                    "Agrupar abiertas por",
                    options=[
                        OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH,
                        OPEN_ISSUES_FOCUS_MODE_MAESTRAS,
                    ],
                    format_func=lambda mode: (
                        "Criticidad alta (Impedimento / High / Highest)"
                        if str(mode) == OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH
                        else "Incidencias maestras"
                    ),
                    horizontal=False,
                    key="cfg_open_issues_focus_mode",
                )
                st.caption(
                    "Aplica de forma centralizada en Insights, scopes quincenales "
                    "y el informe Seguimiento del periodo."
                )

            with st.container(border=True, key="cfg_prefs_card_ppt"):
                st.markdown("#### Descargas del informe PPT")
                st.markdown("**Carpeta de guardado**")
                default_download_dir = str((Path.home() / "Downloads").expanduser())
                report_ppt_download_dir_default = (
                    str(getattr(settings, "REPORT_PPT_DOWNLOAD_DIR", "") or "").strip()
                    or default_download_dir
                )
                report_ppt_download_dir = st.text_input(
                    "Carpeta de guardado del informe PPT",
                    value=report_ppt_download_dir_default,
                    key="cfg_report_ppt_download_dir",
                    label_visibility="collapsed",
                    placeholder=default_download_dir,
                )
                st.markdown("**Plantilla informe seguimiento**")
                period_template_default = str(
                    getattr(settings, "PERIOD_PPT_TEMPLATE_PATH", "") or ""
                ).strip() or str(suggested_period_ppt_template_path(settings))
                period_ppt_template_path = st.text_input(
                    "Ruta de plantilla PPT seguimiento",
                    value=period_template_default,
                    key="cfg_period_ppt_template_path",
                    label_visibility="collapsed",
                )
                template_exists = (
                    Path(str(period_ppt_template_path or "").strip()).expanduser().exists()
                )
                if template_exists:
                    st.caption("Plantilla detectada y lista para el informe de seguimiento.")
                else:
                    st.caption(
                        "La ruta no existe. Si no defines una propia, la app usará la "
                        "plantilla corporativa integrada durante la generación."
                    )

            with st.container(border=True, key="cfg_prefs_card_favs"):
                st.markdown("#### Define los 3 gráficos favoritos")

                catalog = _trend_chart_catalog()
                all_ids = [cid for cid, _ in catalog]
                id_to_label = {cid: label for cid, label in catalog}

                stored = _parse_csv_ids(getattr(settings, "DASHBOARD_SUMMARY_CHARTS", ""), all_ids)
                if not stored:
                    stored = _parse_csv_ids(getattr(settings, "TREND_SELECTED_CHARTS", ""), all_ids)

                fav1_default = stored[0] if len(stored) > 0 else all_ids[0]
                fav2_default = (
                    stored[1]
                    if len(stored) > 1
                    else (all_ids[1] if len(all_ids) > 1 else all_ids[0])
                )
                fav3_default = (
                    stored[2]
                    if len(stored) > 2
                    else (all_ids[2] if len(all_ids) > 2 else all_ids[0])
                )

                c1, c2, c3 = st.columns(3)
                with c1:
                    fav1 = st.selectbox(
                        "Favorito 1",
                        options=all_ids,
                        index=all_ids.index(fav1_default),
                        format_func=lambda x: id_to_label.get(x, x),
                        key="cfg_trend_fav_1",
                    )
                with c2:
                    fav2 = st.selectbox(
                        "Favorito 2",
                        options=all_ids,
                        index=all_ids.index(fav2_default),
                        format_func=lambda x: id_to_label.get(x, x),
                        key="cfg_trend_fav_2",
                    )
                with c3:
                    fav3 = st.selectbox(
                        "Favorito 3",
                        options=all_ids,
                        index=all_ids.index(fav3_default),
                        format_func=lambda x: id_to_label.get(x, x),
                        key="cfg_trend_fav_3",
                    )

            with st.container(border=True, key="cfg_prefs_card_restore"):
                restore_cfg = _render_full_restore_container(key_prefix="cfg_prefs")
            prefs_save_help = None
            if not bool(restore_cfg.get("valid", True)):
                prefs_save_help = (
                    "Completa la confirmación de restauración (checkbox + texto RESTAURAR) "
                    "o limpia esos campos para continuar."
                )
            if st.button(
                "Guardar configuración",
                key="cfg_save_prefs_btn",
                disabled=not bool(restore_cfg.get("valid", True)),
                help=prefs_save_help,
            ):
                if bool(restore_cfg.get("armed", False)):
                    try:
                        restore_env_from_example()
                    except FileNotFoundError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"No se pudo restaurar la configuración: {exc}")
                    else:
                        _clear_restore_widget_state()
                        _queue_all_config_widget_state_clear()
                        _clear_runtime_state_after_restore()
                        st.session_state["__cfg_flash_success"] = (
                            "Configuración restaurada desde la plantilla base."
                        )
                        st.session_state["__cfg_active_tab"] = "Preferencias"
                        st.rerun()
                    return
                summary_csv = ",".join([str(fav1), str(fav2), str(fav3)])
                new_settings = _safe_update_settings(
                    settings,
                    {
                        "THEME": str(theme_mode).strip().lower(),
                        "DASHBOARD_SUMMARY_CHARTS": summary_csv,
                        "TREND_SELECTED_CHARTS": summary_csv,
                        "REPORT_PPT_DOWNLOAD_DIR": str(report_ppt_download_dir).strip(),
                        "PERIOD_PPT_TEMPLATE_PATH": str(period_ppt_template_path).strip(),
                        "ANALYSIS_LOOKBACK_MONTHS": normalize_analysis_lookback_months(
                            analysis_selected_months,
                            default=12,
                        ),
                        "QUINCENA_LAST_FINISHED_ONLY": (
                            "true" if bool(quincena_last_finished_only) else "false"
                        ),
                        "OPEN_ISSUES_FOCUS_MODE": normalize_open_issues_focus_mode(
                            open_issues_focus_mode
                        ),
                    },
                )
                _save_settings_with_migrations(new_settings)
                target_dark_mode = str(theme_mode).strip().lower() == "dark"
                theme_mode_changed = (
                    bool(st.session_state.get("workspace_dark_mode", False)) != target_dark_mode
                )
                if theme_mode_changed:
                    st.session_state["workspace_dark_mode"] = target_dark_mode
                    st.session_state["__cfg_flash_success"] = (
                        "Preferencias guardadas. Modo visual actualizado."
                    )
                else:
                    st.session_state["__cfg_flash_success"] = "Preferencias guardadas."
                st.session_state["__cfg_active_tab"] = "Preferencias"
                st.rerun()

    with t_agg:
        st.markdown("### Orígenes agregados por país")
        st.caption(
            "Esta selección se usa en Vista País (agregada), Insights quincenal y "
            "el informe Seguimiento del periodo. Se recomienda 2 orígenes por país."
        )
        configured_rollup_by_country = country_rollup_sources(settings)
        rollup_selection_by_country: Dict[str, List[str]] = {}
        with st.container(border=True, key="cfg_agg_card_country_rollup"):
            for idx, country in enumerate(countries):
                source_rows = all_configured_sources(settings, country=country)
                options: List[str] = []
                label_by_id: Dict[str, str] = {}
                for src in source_rows:
                    sid = str(src.get("source_id") or "").strip()
                    if not sid:
                        continue
                    alias = str(src.get("alias") or "").strip() or sid
                    source_type = str(src.get("source_type") or "").strip().upper() or "SOURCE"
                    options.append(sid)
                    label_by_id[sid] = f"{alias} · {source_type}"

                if not options:
                    st.markdown(f"**{country}**")
                    st.caption("Sin orígenes configurados para este país.")
                    continue

                configured_ids = [
                    sid
                    for sid in configured_rollup_by_country.get(country, [])[:2]
                    if sid in set(options)
                ]

                def _format_rollup_source_id(
                    source_id: str,
                    *,
                    labels: Dict[str, str] = label_by_id,
                ) -> str:
                    return labels.get(str(source_id), str(source_id))

                selected_ids = st.multiselect(
                    f"{country}",
                    options=options,
                    default=configured_ids,
                    key=f"cfg_rollup_sources_{idx}",
                    format_func=_format_rollup_source_id,
                    max_selections=2,
                )
                selected_clean = [sid for sid in selected_ids if str(sid).strip() in set(options)]
                if selected_clean:
                    rollup_selection_by_country[country] = selected_clean

        if st.button("Guardar configuración", key="cfg_save_rollup_btn"):
            new_settings = _safe_update_settings(
                settings,
                {
                    "COUNTRY_ROLLUP_SOURCES_JSON": _rollup_sources_to_env_json(
                        rollup_selection_by_country
                    )
                },
            )
            _save_settings_with_migrations(new_settings)
            st.session_state["__cfg_flash_success"] = "Agregados guardados."
            st.session_state["__cfg_active_tab"] = "Agregados"
            st.rerun()

    with t_caches:
        st.markdown("### Caches")
        st.caption("Resetea caches persistentes de la aplicación sin afectar la configuración.")

        cache_rows = _rows_from_cache_inventory(settings)
        cache_df = pd.DataFrame(
            cache_rows
            or [
                {
                    "__reset__": False,
                    "__cache_id__": "",
                    "cache": "Sin caches configurados",
                    "registros": 0,
                    "ruta": "",
                }
            ]
        )
        cache_editor = st.data_editor(
            cache_df,
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            key="cfg_cache_reset_editor",
            column_order=["__reset__", "cache", "registros", "ruta"],
            column_config={
                "__reset__": st.column_config.CheckboxColumn("Resetear"),
                "cache": st.column_config.TextColumn("Cache"),
                "registros": st.column_config.NumberColumn("Registros", format="%d"),
                "ruta": st.column_config.TextColumn("Ruta"),
            },
            disabled=["cache", "registros", "ruta"],
        )
        cache_reset_ids, cache_reset_labels = _selected_caches_from_editor(cache_editor)
        cache_reset_cfg = _render_cache_reset_container(
            selected_cache_ids=cache_reset_ids,
            selected_label_by_id=cache_reset_labels,
            key_prefix="cfg_cache",
        )
        cache_reset_disabled = not bool(cache_reset_cfg.get("armed", False))
        if st.button(
            "Resetear caches seleccionados",
            key="cfg_cache_reset_btn",
            disabled=cache_reset_disabled,
            help=(
                "Selecciona caches, marca confirmación y escribe RESETEAR."
                if cache_reset_disabled
                else None
            ),
        ):
            selected_cache_ids = [
                str(x).strip() for x in cache_reset_cfg.get("cache_ids", []) if str(x).strip()
            ]
            results: List[Dict[str, Any]] = []
            for cache_id in selected_cache_ids:
                results.append(reset_cache_store(settings, cache_id))
            try:
                st.cache_data.clear()
            except Exception:
                pass
            clear_signature_cache()
            _clear_cache_reset_widget_state()
            st.session_state["__cfg_cache_reset_results"] = results
            total_reset = sum(int(row.get("reset", 0) or 0) for row in results)
            st.session_state["__cfg_flash_success"] = (
                f"Reset de cache completado ({len(results)} seleccionado(s), {total_reset} registros vaciados)."
            )
            st.session_state["__cfg_active_tab"] = "Cache"
            st.rerun()

        cache_reset_results = st.session_state.pop("__cfg_cache_reset_results", None)
        if isinstance(cache_reset_results, list) and cache_reset_results:
            _render_cache_reset_results(cache_reset_results)

    with t_perf:
        _render_performance_tab(settings=settings)
