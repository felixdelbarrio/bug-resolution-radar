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
    st.session_state["workspace_mode"] = mode
    # Force no preselected dashboard tab while in non-dashboard modes.
    # This lets users return with one click to the desired section.
    if mode in {"ingest", "config"}:
        st.session_state.pop("workspace_section_picker_aux", None)


def _dashboard_labels() -> Dict[str, str]:
    return {
        "overview": "Resumen",
        "issues": "Issues",
        "kanban": "Kanban",
        "trends": "Tendencias",
        "insights": "Insights",
        "notes": "Notas",
    }


def _ensure_scope_state(settings: Settings) -> None:
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
    labels = _dashboard_labels()
    section_names: List[str] = dashboard_page.dashboard_sections()
    default_section = "overview"

    if "workspace_mode" not in st.session_state:
        st.session_state["workspace_mode"] = "dashboard"
    if "workspace_section" not in st.session_state:
        st.session_state["workspace_section"] = default_section
    if "workspace_section_label" not in st.session_state:
        st.session_state["workspace_section_label"] = labels[default_section]

    jump = st.session_state.pop("__jump_to_tab", None)
    if isinstance(jump, str) and jump.strip().lower() in section_names:
        sec = jump.strip().lower()
        st.session_state["workspace_mode"] = "dashboard"
        st.session_state["workspace_section"] = sec
        st.session_state["workspace_section_label"] = labels.get(sec, labels[default_section])


def _render_workspace_header() -> None:
    labels = _dashboard_labels()
    name_by_label = {v: k for k, v in labels.items()}
    section_options = [labels[s] for s in dashboard_page.dashboard_sections()]
    mode = str(st.session_state.get("workspace_mode") or "dashboard")
    current_label = str(st.session_state.get("workspace_section_label") or section_options[0])

    left, right = st.columns([5.0, 0.9], gap="small")

    with left:
        picker_key = (
            "workspace_section_label" if mode == "dashboard" else "workspace_section_picker_aux"
        )
        picked = st.segmented_control(
            "Sección",
            options=section_options,
            selection_mode="single",
            default=current_label if mode == "dashboard" else None,
            key=picker_key,
            label_visibility="collapsed",
        )
        picked_label = str(picked or "")
        if picked_label in name_by_label:
            st.session_state["workspace_section"] = name_by_label.get(picked_label, "overview")
            # Avoid mutating the same key bound to an already-instantiated widget.
            if picker_key != "workspace_section_label":
                st.session_state["workspace_section_label"] = picked_label
            st.session_state["workspace_mode"] = "dashboard"

    with right:
        b_ing, b_cfg = st.columns(2, gap="small")
        b_ing.button(
            "🛰️",
            key="workspace_btn_ingest",
            type="primary" if mode == "ingest" else "secondary",
            use_container_width=True,
            help="Ingesta",
            on_click=_set_workspace_mode,
            args=("ingest",),
        )
        b_cfg.button(
            "⚙️",
            key="workspace_btn_config",
            type="primary" if mode == "config" else "secondary",
            use_container_width=True,
            help="Configuración",
            on_click=_set_workspace_mode,
            args=("config",),
        )


def _render_workspace_scope(settings: Settings) -> None:
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
    ensure_env()
    settings = load_settings()
    hero_title = str(getattr(settings, "APP_TITLE", "") or "").strip()
    if hero_title.lower() in {"", "bug resolution radar"}:
        hero_title = "Cuadro de mando de incidencias"

    st.set_page_config(page_title=hero_title, layout="wide", page_icon="assets/bbva/favicon.png")

    inject_bbva_css()
    render_hero(hero_title)
    _ensure_scope_state(settings)
    _ensure_nav_state()
    with st.container(key="workspace_scope_bar"):
        _render_workspace_scope(settings)
    with st.container(key="workspace_nav_bar"):
        _render_workspace_header()

    mode = str(st.session_state.get("workspace_mode") or "dashboard")
    section = dashboard_page.normalize_dashboard_section(
        str(st.session_state.get("workspace_section") or "overview")
    )

    if mode == "ingest":
        ingest_page.render(settings)
        return
    if mode == "config":
        config_page.render(settings)
        return

    with st.container(key="workspace_dashboard_content"):
        dashboard_page.render(settings, active_section=section)
