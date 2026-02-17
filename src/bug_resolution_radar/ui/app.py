"""Main Streamlit application shell for navigation, scope and global UI state."""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

from bug_resolution_radar.config import (
    Settings,
    all_configured_sources,
    ensure_env,
    load_settings,
    supported_countries,
)
from bug_resolution_radar.ui.pages import config_page, dashboard_page, ingest_page
from bug_resolution_radar.ui.style import inject_bbva_css, render_hero


def _set_workspace_mode(mode: str) -> None:
    """Switch top-level workspace mode and reset transient dashboard picker state."""
    st.session_state["workspace_mode"] = mode


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


def _ensure_scope_state(settings: Settings) -> None:
    """Ensure selected country/source are valid for current configuration."""
    countries = supported_countries(settings)
    default_country = countries[0] if countries else "México"

    if "workspace_country" not in st.session_state:
        st.session_state["workspace_country"] = default_country
    if str(st.session_state.get("workspace_country") or "") not in countries:
        st.session_state["workspace_country"] = default_country

    selected_country = str(st.session_state.get("workspace_country") or default_country)
    source_rows = all_configured_sources(settings, country=selected_country)
    source_ids = [
        str(src.get("source_id") or "").strip() for src in source_rows if src.get("source_id")
    ]

    if "workspace_source_id" not in st.session_state:
        st.session_state["workspace_source_id"] = source_ids[0] if source_ids else ""
    if source_ids and str(st.session_state.get("workspace_source_id") or "") not in source_ids:
        st.session_state["workspace_source_id"] = source_ids[0]
    if not source_ids:
        st.session_state["workspace_source_id"] = ""


def _ensure_nav_state() -> None:
    """Initialize and keep navigation state consistent across reruns and jumps."""
    labels = _dashboard_labels()
    name_by_label = {label: name for name, label in labels.items()}
    section_names: List[str] = dashboard_page.dashboard_sections()
    default_section = "overview" if "overview" in section_names else section_names[0]
    allowed_modes = {"dashboard", "ingest", "config"}

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
    is_dark = bool(st.session_state.get("workspace_dark_mode", False))
    current_section = dashboard_page.normalize_dashboard_section(
        str(st.session_state.get("workspace_section") or "overview")
    )

    left, right = st.columns([5.0, 0.9], gap="small")

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
            b_ing, b_theme, b_cfg = st.columns(3, gap="small")
            b_ing.button(
                "🛰️",
                key="workspace_btn_ingest",
                type="primary" if mode == "ingest" else "secondary",
                width="stretch",
                help="Ingesta",
                on_click=_set_workspace_mode,
                args=("ingest",),
            )
            b_theme.button(
                "◐",
                key="workspace_btn_theme",
                type="primary" if is_dark else "secondary",
                width="stretch",
                help="Tema oscuro",
                on_click=_toggle_dark_mode,
            )
            b_cfg.button(
                "⚙️",
                key="workspace_btn_config",
                type="primary" if mode == "config" else "secondary",
                width="stretch",
                help="Configuración",
                on_click=_set_workspace_mode,
                args=("config",),
            )


def _render_workspace_scope(settings: Settings) -> None:
    """Render country/source selectors used to scope the working dataset."""
    countries = supported_countries(settings)
    if not countries:
        return

    c_country, c_source = st.columns([1.0, 2.0], gap="small")
    with c_country:
        selected_country = st.selectbox("País", options=countries, key="workspace_country")
    source_rows = all_configured_sources(settings, country=selected_country)
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
            )
        else:
            st.selectbox(
                "Origen",
                options=["__none__"],
                key="workspace_source_id_aux",
                format_func=lambda _: "Sin orígenes configurados",
                disabled=True,
            )


def main() -> None:
    """Boot application, render hero/shell and dispatch the selected page."""
    ensure_env()
    settings = load_settings()
    hero_title = str(getattr(settings, "APP_TITLE", "") or "").strip()
    if hero_title.lower() in {"", "bug resolution radar"}:
        hero_title = "Cuadro de mando de incidencias"

    st.set_page_config(page_title=hero_title, layout="wide", page_icon="assets/bbva/favicon.png")

    if "workspace_dark_mode" not in st.session_state:
        st.session_state["workspace_dark_mode"] = False

    inject_bbva_css(dark_mode=bool(st.session_state.get("workspace_dark_mode", False)))
    render_hero(hero_title)
    _ensure_scope_state(settings)
    _ensure_nav_state()
    section_before_header = dashboard_page.normalize_dashboard_section(
        str(st.session_state.get("workspace_section") or "overview")
    )
    with st.container(key="workspace_scope_bar"):
        _render_workspace_scope(settings)
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
        return
    if mode == "config":
        config_page.render(settings)
        return

    with st.container(key=f"workspace_dashboard_content_{section}"):
        dashboard_page.render(settings, active_section=section)
