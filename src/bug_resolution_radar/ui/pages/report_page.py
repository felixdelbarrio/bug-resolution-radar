"""Report generation UI page for scoped executive PowerPoint exports."""

from __future__ import annotations

import base64
import json

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as components_html

from bug_resolution_radar.config import Settings
from bug_resolution_radar.reports import ExecutiveReportResult, generate_scope_executive_ppt
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)

_REPORT_STATE_KEY = "workspace_report_payload"


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


def _store_result(result: ExecutiveReportResult, *, country: str, source_id: str) -> None:
    st.session_state[_REPORT_STATE_KEY] = {
        "scope_key": _scope_key(country, source_id),
        "result": result,
    }


def _load_result_for_scope(country: str, source_id: str) -> ExecutiveReportResult | None:
    payload = st.session_state.get(_REPORT_STATE_KEY)
    if not isinstance(payload, dict):
        return None
    if str(payload.get("scope_key") or "") != _scope_key(country, source_id):
        return None
    result = payload.get("result")
    return result if isinstance(result, ExecutiveReportResult) else None


def _auto_download(result: ExecutiveReportResult) -> None:
    payload = base64.b64encode(result.content).decode("ascii")
    meta = json.dumps(
        {
            "b64": payload,
            "file_name": result.file_name,
            "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
    country, source_id = _current_scope()
    st.subheader("Informe ejecutivo PPT")
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

    filters_summary = [
        f"Estado={len(status_filters)}",
        f"Prioridad={len(priority_filters)}",
        f"Assignee={len(assignee_filters)}",
    ]
    st.info(f"Scope activo: {country or 'Sin país'} · {source_id} · Filtros: {' | '.join(filters_summary)}")

    trigger = st.button(
        "📥 Generar y descargar informe (1 clic)",
        key="btn_generate_download_scope_ppt",
        type="primary",
        width="stretch",
    )

    if trigger:
        try:
            with st.spinner("Preparando gráficos e insights del scope activo..."):
                all_df = load_issues_df(settings.DATA_PATH)
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

            _store_result(result, country=country, source_id=source_id)
            _auto_download(result)
            st.success(
                f"Informe generado y descarga lanzada: {result.slide_count} slides · "
                f"{result.total_issues} issues ({result.open_issues} abiertas)."
            )
        except Exception as exc:
            st.error(f"No se pudo generar/descargar la PPT para el scope activo: {exc}")

    result = _load_result_for_scope(country, source_id)
    if result is None:
        st.caption("Aún no se ha generado informe para este scope.")
        return

    st.caption(
        f"Último informe: `{result.file_name}` · Filtros aplicados: {result.applied_filter_summary}"
    )

    # Fallback manual in case browser blocks auto-download.
    st.download_button(
        "Descarga manual (si tu navegador bloqueó la automática)",
        data=result.content,
        file_name=result.file_name,
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        key="btn_download_scope_ppt_fallback",
        type="secondary",
        width="stretch",
    )
