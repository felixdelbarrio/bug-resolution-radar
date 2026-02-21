"""Report generation UI page for scoped executive PowerPoint exports."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from bug_resolution_radar.analysis_window import (
    effective_analysis_lookback_months,
    max_available_backlog_months,
    parse_analysis_lookback_months,
)
from bug_resolution_radar.config import Settings, config_home
from bug_resolution_radar.reports import generate_scope_executive_ppt
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)

_REPORT_STATUS_KEY = "workspace_report_status"
_REPORT_SAVED_PATH_KEY_PREFIX = "workspace_report_saved_path"
_REPORT_SAVE_DONE_KEY_PREFIX = "workspace_report_save_done"


def _default_report_export_dir() -> Path:
    """Pick a user-friendly, writable export directory for local builds."""
    candidates = [
        Path.home() / "Downloads",
        config_home() / "exports",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if candidate.is_dir():
                return candidate
        except Exception:
            continue
    return Path.cwd()


def _unique_export_path(export_dir: Path, *, file_name: str) -> Path:
    name = str(file_name or "").strip() or "radar-export.pptx"
    target = export_dir / name
    if not target.exists():
        return target
    stem = target.stem or "radar-export"
    suffix = target.suffix or ".pptx"
    for i in range(1, 1000):
        candidate = export_dir / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    return export_dir / f"{stem}_{os.getpid()}{suffix}"


def _reveal_in_file_manager(path: Path) -> None:
    try:
        import subprocess

        target_path = Path(path)
        target_dir = target_path.parent if str(target_path.parent) else Path.cwd()
        if sys.platform == "darwin":
            if target_path.exists():
                subprocess.Popen(["open", "-R", str(target_path)])
            else:
                subprocess.Popen(["open", str(target_dir)])
            return
        if os.name == "nt":
            if target_path.exists():
                subprocess.Popen(["explorer", "/select,", str(target_path)])
            else:
                subprocess.Popen(["explorer", str(target_dir)])
            return
        subprocess.Popen(["xdg-open", str(target_dir)])
    except Exception:
        return


def _scope_key(country: str, source_id: str) -> str:
    return f"{str(country or '').strip()}::{str(source_id or '').strip()}"


def _current_scope() -> tuple[str, str]:
    country = str(st.session_state.get("workspace_country") or "").strip()
    source_id = str(st.session_state.get("workspace_source_id") or "").strip()
    return country, source_id


def _scope_df(df: pd.DataFrame, *, country: str, source_id: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)
    if country and "country" in df.columns:
        mask &= df["country"].fillna("").astype(str).eq(country)
    if source_id and "source_id" in df.columns:
        mask &= df["source_id"].fillna("").astype(str).eq(source_id)
    return df.loc[mask].copy(deep=False)


def _analysis_window_label(settings: Settings, *, scoped_df: pd.DataFrame) -> str:
    if scoped_df is None or scoped_df.empty:
        configured = parse_analysis_lookback_months(settings)
        if configured > 0:
            return f"Ventana={int(configured)} meses"
        return "Ventana=histórico completo"

    available = int(max_available_backlog_months(scoped_df))
    effective = int(effective_analysis_lookback_months(settings, df=scoped_df))
    if effective >= available:
        return f"Ventana=histórico completo ({available} meses)"
    return f"Ventana={effective} de {available} meses"


def _visible_filter_label(values: list[str], *, name: str) -> str:
    clean = [str(v or "").strip() for v in list(values or []) if str(v or "").strip()]
    if not clean:
        return f"{name}=Todos"
    if len(clean) <= 3:
        return f"{name}={', '.join(clean)}"
    return f"{name}={', '.join(clean[:3])} (+{len(clean) - 3})"


def _saved_path_state_key(scope_key: str) -> str:
    return f"{_REPORT_SAVED_PATH_KEY_PREFIX}::{scope_key}"


def _save_done_state_key(scope_key: str) -> str:
    return f"{_REPORT_SAVE_DONE_KEY_PREFIX}::{scope_key}"


def _store_status(*, scope_key: str, kind: str, message: str) -> None:
    st.session_state[_REPORT_STATUS_KEY] = {
        "scope_key": str(scope_key or "").strip(),
        "kind": str(kind or "info").strip().lower(),
        "message": str(message or "").strip(),
    }


def _render_status(scope_key: str) -> None:
    payload = st.session_state.get(_REPORT_STATUS_KEY)
    if not isinstance(payload, dict):
        return
    if str(payload.get("scope_key") or "") != str(scope_key or "").strip():
        return

    level = str(payload.get("kind") or "info").strip().lower()
    message = str(payload.get("message") or "").strip()

    if level == "success":
        st.success(message or "Informe guardado.")
    elif level == "error":
        st.error(message or "No se pudo guardar el informe.")
    else:
        st.info(message or "Estado de informe actualizado.")

    saved_path_value = str(st.session_state.get(_saved_path_state_key(scope_key)) or "").strip()
    if saved_path_value:
        label_col, path_col = st.columns([0.25, 0.75], gap="small")
        with label_col:
            st.caption("Último guardado local:")
        with path_col:
            with st.container(key="workspace_report_saved_path_link"):
                if st.button(
                    saved_path_value,
                    key=f"btn_open_saved_report::{scope_key}::{saved_path_value}",
                    type="secondary",
                    width="content",
                    help="Abrir carpeta del informe",
                ):
                    _reveal_in_file_manager(Path(saved_path_value))


def render(settings: Settings) -> None:
    """Render one-click executive report generation for selected scope + active filters."""
    country, source_id = _current_scope()
    st.subheader("Informe PPT")
    st.caption(
        "Generación todo-en-uno: usa exactamente el mismo scope, filtros, gráficos y leyendas "
        "que estás viendo en la aplicación."
    )

    if not source_id:
        st.warning("Selecciona un origen en el scope superior para generar el informe.")
        return

    status_filters = list(st.session_state.get(FILTER_STATUS_KEY) or [])
    priority_filters = list(st.session_state.get(FILTER_PRIORITY_KEY) or [])
    assignee_filters = list(st.session_state.get(FILTER_ASSIGNEE_KEY) or [])

    all_df_for_scope: pd.DataFrame | None = None
    scoped_for_scope = pd.DataFrame()
    try:
        all_df_for_scope = load_issues_df(settings.DATA_PATH)
        scoped_for_scope = _scope_df(all_df_for_scope, country=country, source_id=source_id)
    except Exception:
        scoped_for_scope = pd.DataFrame()

    filters_summary = [
        _analysis_window_label(settings, scoped_df=scoped_for_scope),
        _visible_filter_label(status_filters, name="Estado"),
        _visible_filter_label(priority_filters, name="Prioridad"),
        _visible_filter_label(assignee_filters, name="Responsable"),
    ]
    st.info(
        f"Scope activo: {country or 'Sin país'} · {source_id} · Filtros: {' | '.join(filters_summary)}"
    )
    scope_key = _scope_key(country, source_id)
    save_done_key = _save_done_state_key(scope_key)

    export_dir = _default_report_export_dir()
    export_dir_label = str(export_dir)

    button_slot = st.empty()
    run_save = False
    if not bool(st.session_state.get(save_done_key, False)):
        with button_slot:
            run_save = st.button(
                "Guardar en disco",
                key=f"btn_save_scope_ppt_{scope_key}",
                type="primary",
                width="content",
                help=f"Guarda el PPT en: {export_dir_label}",
            )

    if run_save:
        saved_ok = False
        try:
            with st.spinner("Generando el informe PPT del scope activo..."):
                all_df = (
                    all_df_for_scope
                    if all_df_for_scope is not None
                    else load_issues_df(settings.DATA_PATH)
                )
                scoped_df = _scope_df(all_df, country=country, source_id=source_id)
                if scoped_df.empty:
                    raise ValueError("No hay datos en el scope seleccionado.")

                ctx = build_dashboard_data_context(
                    df_all=scoped_df,
                    settings=settings,
                    include_kpis=True,
                )

                result = generate_scope_executive_ppt(
                    settings,
                    country=country,
                    source_id=source_id,
                    status_filters=status_filters,
                    priority_filters=priority_filters,
                    assignee_filters=assignee_filters,
                    dff_override=ctx.dff,
                    open_df_override=ctx.open_df,
                    scoped_source_df_override=scoped_df,
                )

                export_path = _unique_export_path(export_dir, file_name=result.file_name)
                export_path.write_bytes(result.content)
                st.session_state[_saved_path_state_key(scope_key)] = str(export_path)
                saved_ok = True

            _store_status(
                scope_key=scope_key,
                kind="success",
                message=(
                    f"Informe guardado · {result.slide_count} slides · "
                    f"{result.total_issues} issues ({result.open_issues} abiertas)."
                ),
            )
        except Exception as exc:
            _store_status(
                scope_key=scope_key,
                kind="error",
                message=f"No se pudo generar/guardar el informe PPT: {exc}",
            )
        if saved_ok:
            st.session_state[save_done_key] = True
            button_slot.empty()

    status_slot = st.empty()
    with status_slot:
        _render_status(scope_key)
