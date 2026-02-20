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
from bug_resolution_radar.reports import ExecutiveReportResult, generate_scope_executive_ppt
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)

_REPORT_ALERT_KEY = "workspace_report_alert"
_PPT_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


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
        if sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", "-R", str(path)])
            return
        if os.name == "nt":
            import subprocess

            subprocess.Popen(["explorer", "/select,", str(path)])
            return
        import subprocess

        subprocess.Popen(["xdg-open", str(path.parent)])
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


def _store_alert(
    *,
    country: str,
    source_id: str,
    kind: str,
    message: str,
    result: ExecutiveReportResult | None = None,
) -> None:
    st.session_state[_REPORT_ALERT_KEY] = {
        "scope_key": _scope_key(country, source_id),
        "kind": str(kind or "info").strip().lower(),
        "message": str(message or "").strip(),
        "result": result,
    }


def _load_alert_for_scope(country: str, source_id: str) -> dict | None:
    payload = st.session_state.get(_REPORT_ALERT_KEY)
    if not isinstance(payload, dict):
        return None
    if str(payload.get("scope_key") or "") != _scope_key(country, source_id):
        return None
    return payload


def _clear_alert() -> None:
    st.session_state.pop(_REPORT_ALERT_KEY, None)


def _render_alert(country: str, source_id: str) -> None:
    payload = _load_alert_for_scope(country, source_id)
    if not isinstance(payload, dict):
        return

    level = str(payload.get("kind") or "info").strip().lower()
    message = str(payload.get("message") or "").strip()
    result = payload.get("result")

    scope_key = _scope_key(country, source_id)
    saved_path_state_key = f"workspace_report_saved_path::{scope_key}"
    saved_path_value = str(st.session_state.get(saved_path_state_key) or "").strip()

    content_col, close_col = st.columns([0.96, 0.04], gap="small")
    with content_col:
        if level == "success":
            st.success(message or "Informe generado.")
        elif level == "error":
            st.error(message or "No se pudo generar el informe.")
        else:
            st.info(message or "Estado de informe actualizado.")

        if isinstance(result, ExecutiveReportResult):
            st.caption(
                "Si la descarga falla en la build (pestaña nueva con spinner), usa 'Guardar en disco'."
            )
            a1, a2, a3 = st.columns([1.0, 1.0, 1.0], gap="small")
            with a1:
                st.download_button(
                    "Descarga manual",
                    data=result.content,
                    file_name=result.file_name,
                    mime=_PPT_MIME,
                    key=f"btn_download_scope_ppt_alert_{scope_key}",
                    type="secondary",
                    width="content",
                )
            with a2:
                if st.button(
                    "Guardar en disco",
                    key=f"btn_save_scope_ppt_alert_{scope_key}",
                    type="secondary",
                    width="content",
                    help="Guarda el PPT en una carpeta local (por defecto, Descargas).",
                ):
                    try:
                        export_dir = _default_report_export_dir()
                        export_path = _unique_export_path(export_dir, file_name=result.file_name)
                        export_path.write_bytes(result.content)
                        st.session_state[saved_path_state_key] = str(export_path)
                        saved_path_value = str(export_path)
                        st.success(f"Informe guardado en: {export_path}")
                    except Exception as exc:
                        st.error(f"No se pudo guardar el informe en disco: {exc}")
            with a3:
                if st.button(
                    "Abrir carpeta",
                    key=f"btn_reveal_scope_ppt_alert_{scope_key}",
                    type="secondary",
                    width="content",
                    disabled=not bool(saved_path_value),
                    help="Abre Finder/Explorer en el archivo guardado.",
                ):
                    try:
                        _reveal_in_file_manager(Path(saved_path_value))
                    except Exception:
                        pass
            if saved_path_value:
                st.caption(f"Último guardado local: {saved_path_value}")
    with close_col:
        if st.button(
            "✕",
            key=f"btn_close_report_alert_{scope_key}",
            help="Cerrar alerta",
            type="secondary",
        ):
            _clear_alert()
            st.rerun()


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
    _render_alert(country, source_id)

    run_generation = st.button(
        "Generar informe",
        key=f"btn_generate_scope_ppt_{_scope_key(country, source_id)}",
        type="primary",
        width="content",
        help="Genera el PPT y habilita la descarga manual en esta misma pantalla.",
    )

    if run_generation:
        try:
            with st.spinner("Preparando gráficos e insights del scope activo..."):
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

            if getattr(sys, "frozen", False):
                try:
                    export_dir = _default_report_export_dir()
                    export_path = _unique_export_path(export_dir, file_name=result.file_name)
                    export_path.write_bytes(result.content)
                    st.session_state[
                        f"workspace_report_saved_path::{_scope_key(country, source_id)}"
                    ] = str(export_path)
                except Exception:
                    pass

            _store_alert(
                country=country,
                source_id=source_id,
                kind="success",
                message=(
                    f"Informe generado: {result.slide_count} slides · "
                    f"{result.total_issues} issues ({result.open_issues} abiertas)."
                ),
                result=result,
            )
        except Exception as exc:
            _store_alert(
                country=country,
                source_id=source_id,
                kind="error",
                message=f"No se pudo generar/descargar la PPT para el scope activo: {exc}",
                result=None,
            )
        st.rerun()
