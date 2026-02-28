"""Main Streamlit application shell for navigation, scope and global UI state."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

import streamlit as st
from streamlit import config as st_config

from bug_resolution_radar.config import (
    Settings,
    all_configured_sources,
    ensure_env,
    load_settings,
    save_settings,
)
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.dashboard.state import (
    bootstrap_filters_from_env,
    clear_all_filters,
    persist_filters_in_env,
)
from bug_resolution_radar.ui.pages import config_page, dashboard_page, ingest_page, report_page
from bug_resolution_radar.ui.style import inject_bbva_css, render_hero


def _sync_settings_to_process_env(settings: Settings) -> None:
    """
    Keep runtime `os.environ` aligned with `.env` values already parsed into Settings.

    Some ingestion modules read configuration via `os.getenv(...)` directly. In the
    Streamlit app we load `.env` through `load_settings()` (without exporting vars),
    so this bridge avoids mismatches between what the UI shows and what backend
    ingestion code reads.
    """
    for key, value in settings.model_dump().items():
        if value is None:
            os.environ.pop(str(key), None)
            continue
        os.environ[str(key)] = str(value)


def _set_workspace_mode(mode: str) -> None:
    """Switch top-level workspace mode and reset transient dashboard picker state."""
    mode_txt = str(mode or "").strip().lower()
    previous_mode = str(st.session_state.get("workspace_mode") or "").strip().lower()
    if mode_txt == "report" and previous_mode != "report":
        report_state_prefixes = (
            "workspace_report_save_done::",  # legacy
            "workspace_report_saved_path::",
            "workspace_report_phase::",
            "workspace_report_request_sig::",
            "workspace_report_artifact::",
        )
        for key in list(st.session_state.keys()):
            key_txt = str(key or "")
            if key_txt == "workspace_report_status" or key_txt.startswith(report_state_prefixes):
                st.session_state.pop(key, None)
    st.session_state["workspace_mode"] = mode_txt


def _dashboard_labels() -> Dict[str, str]:
    """Map internal dashboard section ids to visible labels."""
    return {
        "overview": "Resumen",
        "issues": "Issues",
        "kanban": "Kanban",
        "trends": "Tendencias",
        "insights": "Insights",
        "notes": "Notas",
    }


def _reset_scope_filters() -> None:
    """Reset dashboard filters whenever workspace scope changes."""
    clear_all_filters()
    st.session_state.pop("__filters_action_context", None)
    suffixes = ("filter_status_ui", "filter_priority_ui", "filter_assignee_ui")
    for key in list(st.session_state.keys()):
        key_txt = str(key or "")
        if key_txt in suffixes:
            st.session_state.pop(key, None)
            continue
        if any(key_txt.endswith(f"::{suffix}") for suffix in suffixes):
            st.session_state.pop(key, None)


def _on_workspace_scope_change() -> None:
    """Handle country/source changes by clearing active analysis filters."""
    _reset_scope_filters()


def _sources_with_results(
    settings: Settings,
    *,
    configured_sources: List[Dict[str, str]] | None = None,
) -> List[Dict[str, str]]:
    """Return configured sources that currently have ingested rows."""
    source_rows = (
        configured_sources if configured_sources is not None else all_configured_sources(settings)
    )
    if not source_rows:
        return []

    try:
        df = load_issues_df(settings.DATA_PATH)
    except Exception:
        # If data cannot be loaded, keep configured options available.
        return source_rows
    if df.empty:
        return []

    has_source_id_column = "source_id" in df.columns
    if not has_source_id_column:
        return []

    source_ids = df["source_id"].dropna().astype(str).str.strip()
    source_ids_with_results = {sid for sid in source_ids.unique().tolist() if sid}

    filtered_sources: List[Dict[str, str]] = []
    for src in source_rows:
        sid = str(src.get("source_id") or "").strip()

        if sid and sid in source_ids_with_results:
            filtered_sources.append(src)

    return filtered_sources


def _sources_with_results_by_country(settings: Settings) -> Dict[str, List[Dict[str, str]]]:
    """Group result-backed sources by country while preserving configuration order."""
    grouped: Dict[str, List[Dict[str, str]]] = {}
    configured_sources = all_configured_sources(settings)
    for src in _sources_with_results(settings, configured_sources=configured_sources):
        country = str(src.get("country") or "").strip()
        if not country:
            continue
        grouped.setdefault(country, []).append(src)
    return grouped


def _ensure_scope_state(settings: Settings) -> Dict[str, List[Dict[str, str]]]:
    """Ensure selected country/source are valid for current configuration."""
    sources_by_country = _sources_with_results_by_country(settings)
    countries = list(sources_by_country.keys())
    default_country = countries[0] if countries else ""

    if not countries:
        st.session_state["workspace_country"] = ""
        st.session_state["workspace_source_id"] = ""
        return {}

    if "workspace_country" not in st.session_state:
        st.session_state["workspace_country"] = default_country
    if str(st.session_state.get("workspace_country") or "") not in countries:
        st.session_state["workspace_country"] = default_country

    selected_country = str(st.session_state.get("workspace_country") or default_country)
    source_rows = sources_by_country.get(selected_country, [])
    source_ids = [
        str(src.get("source_id") or "").strip() for src in source_rows if src.get("source_id")
    ]

    if "workspace_source_id" not in st.session_state:
        st.session_state["workspace_source_id"] = source_ids[0] if source_ids else ""
    if source_ids and str(st.session_state.get("workspace_source_id") or "") not in source_ids:
        st.session_state["workspace_source_id"] = source_ids[0]
    if not source_ids:
        st.session_state["workspace_source_id"] = ""
    return sources_by_country


def _ensure_nav_state() -> None:
    """Initialize and keep navigation state consistent across reruns and jumps."""
    labels = _dashboard_labels()
    name_by_label = {label: name for name, label in labels.items()}
    section_names: List[str] = dashboard_page.dashboard_sections()
    default_section = "overview" if "overview" in section_names else section_names[0]
    allowed_modes = {"dashboard", "report", "ingest", "config"}

    if "workspace_mode" not in st.session_state:
        st.session_state["workspace_mode"] = "dashboard"
    mode = str(st.session_state.get("workspace_mode") or "dashboard").strip().lower()
    st.session_state["workspace_mode"] = mode if mode in allowed_modes else "dashboard"

    section = str(st.session_state.get("workspace_section") or default_section).strip().lower()
    if section not in section_names:
        section = default_section

    selected_label = str(st.session_state.get("workspace_section_label") or "").strip()
    selected_from_label = name_by_label.get(selected_label)
    if selected_from_label in section_names:
        section = str(selected_from_label)

    jump = st.session_state.pop("__jump_to_tab", None)
    if isinstance(jump, str) and jump.strip().lower() in section_names:
        sec = jump.strip().lower()
        st.session_state["workspace_mode"] = "dashboard"
        section = sec

    st.session_state["workspace_section"] = section
    st.session_state["workspace_section_label"] = labels.get(section, labels[default_section])


def _toggle_dark_mode() -> None:
    """Toggle global dark theme mode."""
    st.session_state["workspace_dark_mode"] = not bool(
        st.session_state.get("workspace_dark_mode", False)
    )
    _persist_theme_preference_in_env(bool(st.session_state.get("workspace_dark_mode", False)))


def _theme_pref_to_dark_mode(theme_pref: str, *, fallback: bool = False) -> bool:
    pref = str(theme_pref or "").strip().lower()
    if pref == "dark":
        return True
    if pref == "light":
        return False
    return fallback


def _persist_theme_preference_in_env(is_dark: bool) -> None:
    desired_theme = "dark" if bool(is_dark) else "light"
    settings = load_settings()
    current_theme = str(getattr(settings, "THEME", "") or "").strip().lower()
    if current_theme == desired_theme:
        return
    save_settings(settings.model_copy(update={"THEME": desired_theme}))


def _sync_streamlit_theme_from_workspace() -> bool:
    """Sync Streamlit's runtime theme with workspace dark/light mode."""
    is_dark = bool(st.session_state.get("workspace_dark_mode", False))
    desired = (
        {
            "theme.base": "dark",
            "theme.primaryColor": "#5F9FFF",
            "theme.backgroundColor": "#0A1228",
            "theme.secondaryBackgroundColor": "#1A2B47",
            "theme.textColor": "#EAF0FF",
            "theme.font": "sans serif",
        }
        if is_dark
        else {
            "theme.base": "light",
            "theme.primaryColor": "#0051F1",
            "theme.backgroundColor": "#F4F6F9",
            "theme.secondaryBackgroundColor": "#FFFFFF",
            "theme.textColor": "#11192D",
            "theme.font": "sans serif",
        }
    )

    changed = False
    for key, value in desired.items():
        current = st_config.get_option(key)
        if str(current or "").strip().lower() != str(value).strip().lower():
            st_config.set_option(key, value)
            changed = True

    return changed


def _set_workspace_section(section: str) -> None:
    """Activate a dashboard section from top-level workspace navigation."""
    labels = _dashboard_labels()
    section_names: List[str] = dashboard_page.dashboard_sections()
    if not section_names:
        return
    normalized = str(section or "").strip().lower()
    if normalized not in section_names:
        normalized = "overview" if "overview" in section_names else section_names[0]
    st.session_state["workspace_mode"] = "dashboard"
    st.session_state["workspace_section"] = normalized
    st.session_state["workspace_section_label"] = labels.get(
        normalized, labels.get(section_names[0], "Resumen")
    )


def _render_workspace_header() -> None:
    """Render top navigation bar and action icons."""
    labels = _dashboard_labels()
    name_by_label = {v: k for k, v in labels.items()}
    section_options = [labels[s] for s in dashboard_page.dashboard_sections()]
    if not section_options:
        return
    mode = str(st.session_state.get("workspace_mode") or "dashboard")
    current_section = dashboard_page.normalize_dashboard_section(
        str(st.session_state.get("workspace_section") or "overview")
    )
    is_dark_mode = bool(st.session_state.get("workspace_dark_mode", False))

    left, right = st.columns([5.0, 1.3], gap="small")

    with left:
        with st.container(key="workspace_nav_tabs"):
            tab_cols = st.columns(len(section_options), gap="small")
            for idx, label in enumerate(section_options):
                section_name = name_by_label.get(label, "overview")
                tab_cols[idx].button(
                    label,
                    key=f"workspace_tab_{section_name}",
                    type=(
                        "primary"
                        if mode == "dashboard" and section_name == current_section
                        else "secondary"
                    ),
                    width="stretch",
                    on_click=_set_workspace_section,
                    args=(section_name,),
                )

    with right:
        with st.container(key="workspace_nav_actions"):
            b_rep, b_ing, b_theme, b_cfg = st.columns(4, gap="small")
            # Keep labels visually empty: icons are injected via CSS and tooltips provide semantics.
            icon_label = "\u00a0"
            with b_rep:
                with st.container(key="workspace_btn_slot_report"):
                    st.button(
                        icon_label,
                        key="workspace_btn_report",
                        type="primary" if mode == "report" else "secondary",
                        width="stretch",
                        help="Informe PPT",
                        on_click=_set_workspace_mode,
                        args=("report",),
                    )
            with b_ing:
                with st.container(key="workspace_btn_slot_ingest"):
                    st.button(
                        icon_label,
                        key="workspace_btn_ingest",
                        type="primary" if mode == "ingest" else "secondary",
                        width="stretch",
                        help="Ingesta",
                        on_click=_set_workspace_mode,
                        args=("ingest",),
                    )
            with b_theme:
                with st.container(key="workspace_btn_slot_theme"):
                    st.button(
                        icon_label,
                        key="workspace_btn_theme",
                        type="secondary",
                        width="stretch",
                        help="Cambiar a tema claro" if is_dark_mode else "Cambiar a tema oscuro",
                        on_click=_toggle_dark_mode,
                    )
            with b_cfg:
                with st.container(key="workspace_btn_slot_config"):
                    st.button(
                        icon_label,
                        key="workspace_btn_config",
                        type="primary" if mode == "config" else "secondary",
                        width="stretch",
                        help="Configuración",
                        on_click=_set_workspace_mode,
                        args=("config",),
                    )


def _render_workspace_scope(
    settings: Settings,
    *,
    sources_by_country: Dict[str, List[Dict[str, str]]] | None = None,
) -> None:
    """Render country/source selectors used to scope the working dataset."""
    scoped_sources = sources_by_country or _sources_with_results_by_country(settings)
    countries = list(scoped_sources.keys())
    if not countries:
        return

    c_country, c_source = st.columns([1.0, 2.0], gap="small")
    with c_country:
        selected_country = st.selectbox(
            "País",
            options=countries,
            key="workspace_country",
            on_change=_on_workspace_scope_change,
        )
    source_rows = scoped_sources.get(selected_country, [])
    source_ids = [
        str(src.get("source_id") or "").strip() for src in source_rows if src.get("source_id")
    ]
    source_label_by_id: Dict[str, str] = {}
    for src in source_rows:
        sid = str(src.get("source_id") or "").strip()
        alias = str(src.get("alias") or "").strip()
        source_type = str(src.get("source_type") or "").strip().upper() or "SOURCE"
        if sid:
            source_label_by_id[sid] = f"{alias} · {source_type}"

    with c_source:
        if source_ids:
            if str(st.session_state.get("workspace_source_id") or "") not in source_ids:
                st.session_state["workspace_source_id"] = source_ids[0]
            st.selectbox(
                "Origen",
                options=source_ids,
                key="workspace_source_id",
                format_func=lambda sid: source_label_by_id.get(str(sid), str(sid)),
                on_change=_on_workspace_scope_change,
            )
        else:
            st.selectbox(
                "Origen",
                options=["__none__"],
                key="workspace_source_id_aux",
                format_func=lambda _: "Sin orígenes con resultados",
                disabled=True,
            )


def _page_favicon() -> str:
    icon_path = (
        Path(__file__).resolve().parent
        / "assets"
        / "icons"
        / "bbva"
        / "spherica-behavioural-economics.svg"
    )
    return str(icon_path) if icon_path.exists() else "📡"


def main() -> None:
    """Boot application, render hero/shell and dispatch the selected page."""
    ensure_env()
    settings = load_settings()
    _sync_settings_to_process_env(settings)
    bootstrap_filters_from_env(settings)
    if "workspace_dark_mode" not in st.session_state:
        streamlit_dark_fallback = (
            str(st_config.get_option("theme.base") or "").strip().lower() == "dark"
        )
        st.session_state["workspace_dark_mode"] = _theme_pref_to_dark_mode(
            str(getattr(settings, "THEME", "auto") or "auto"),
            fallback=streamlit_dark_fallback,
        )
    hero_title = str(getattr(settings, "APP_TITLE", "") or "").strip()
    if hero_title.lower() in {"", "bug resolution radar"}:
        hero_title = "Cuadro de mando de incidencias"

    st.set_page_config(page_title=hero_title, page_icon=_page_favicon(), layout="wide")

    theme_changed = _sync_streamlit_theme_from_workspace()
    theme_rerun_key = "__theme_config_sync_rerun"
    if theme_changed:
        # Streamlit applies some theme settings on the next rerun; force it once so
        # users don't need to click twice when switching light/dark.
        if not bool(st.session_state.get(theme_rerun_key, False)):
            st.session_state[theme_rerun_key] = True
            st.rerun()
        else:
            # Avoid rerun loops if a runtime/host ignores theme updates.
            st.session_state.pop(theme_rerun_key, None)
    else:
        st.session_state.pop(theme_rerun_key, None)

    inject_bbva_css(dark_mode=bool(st.session_state.get("workspace_dark_mode", False)))
    render_hero(hero_title)
    sources_by_country = _ensure_scope_state(settings)
    _ensure_nav_state()
    section_before_header = dashboard_page.normalize_dashboard_section(
        str(st.session_state.get("workspace_section") or "overview")
    )
    with st.container(key="workspace_scope_bar"):
        _render_workspace_scope(settings, sources_by_country=sources_by_country)
    with st.container(key=f"workspace_nav_bar_{section_before_header}"):
        _render_workspace_header()

    mode = str(st.session_state.get("workspace_mode") or "dashboard")
    section = dashboard_page.normalize_dashboard_section(
        str(st.session_state.get("workspace_section") or "overview")
    )
    if mode == "dashboard" and section != section_before_header:
        st.rerun()

    if mode == "ingest":
        ingest_page.render(settings)
    elif mode == "report":
        report_page.render(settings)
    elif mode == "config":
        config_page.render(settings)
    else:
        with st.container(key=f"workspace_dashboard_content_{section}"):
            dashboard_page.render(settings, active_section=section)

    persist_filters_in_env(settings)
