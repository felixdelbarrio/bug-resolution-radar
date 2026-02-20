"""Report generation UI page for scoped executive PowerPoint exports."""

from __future__ import annotations

import base64
import json

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as components_html

from bug_resolution_radar.analysis_window import (
    effective_analysis_lookback_months,
    max_available_backlog_months,
    parse_analysis_lookback_months,
)
from bug_resolution_radar.config import Settings
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

    content_col, close_col = st.columns([0.96, 0.04], gap="small")
    with content_col:
        if level == "success":
            st.success(message or "Informe generado.")
        elif level == "error":
            st.error(message or "No se pudo generar el informe.")
        else:
            st.info(message or "Estado de informe actualizado.")

        if isinstance(result, ExecutiveReportResult):
            st.caption("Si tu navegador bloqueó la descarga automática, usa la descarga manual.")
            st.download_button(
                "Descarga manual",
                data=result.content,
                file_name=result.file_name,
                mime=_PPT_MIME,
                key=f"btn_download_scope_ppt_alert_{_scope_key(country, source_id)}",
                type="secondary",
                width="content",
            )
    with close_col:
        if st.button(
            "✕",
            key=f"btn_close_report_alert_{_scope_key(country, source_id)}",
            help="Cerrar alerta",
            type="secondary",
        ):
            _clear_alert()
            st.rerun()


def _auto_download(result: ExecutiveReportResult) -> None:
    payload = base64.b64encode(result.content).decode("ascii")
    meta = json.dumps(
        {
            "b64": payload,
            "file_name": result.file_name,
            "mime": _PPT_MIME,
        }
    )
    components_html(
        f"""
        <script>
          (function() {{
            const data = {meta};
            const byteChars = atob(data.b64);
            const bytes = new Uint8Array(byteChars.length);
            for (let i = 0; i < byteChars.length; i++) {{
              bytes[i] = byteChars.charCodeAt(i);
            }}
            const blob = new Blob([bytes], {{ type: data.mime }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = data.file_name;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {{ URL.revokeObjectURL(url); a.remove(); }}, 400);
          }})();
        </script>
        """,
        height=0,
        width=0,
    )


def render(settings: Settings) -> None:
    """Render one-click executive report generation for selected scope + active filters."""
    auto_trigger = bool(st.session_state.pop("__report_autorun_requested", False))
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

    run_generation = bool(auto_trigger)

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
                )

            _auto_download(result)
            _store_alert(
                country=country,
                source_id=source_id,
                kind="success",
                message=(
                    f"Informe generado y descarga lanzada: {result.slide_count} slides · "
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
