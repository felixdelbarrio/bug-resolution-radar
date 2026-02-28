"""Report generation UI page for scoped executive PowerPoint exports."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.analysis_window import (
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
_REPORT_PHASE_KEY_PREFIX = "workspace_report_phase"
_REPORT_REQUEST_SIG_KEY_PREFIX = "workspace_report_request_sig"
_REPORT_ARTIFACT_KEY_PREFIX = "workspace_report_artifact"


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _is_macos_protected_user_folder(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    home = Path.home().expanduser().resolve()
    protected_roots = [home / "Desktop", home / "Documents", home / "Downloads"]
    candidate = path.expanduser().resolve()
    for root in protected_roots:
        root_resolved = root.expanduser().resolve()
        if candidate == root_resolved or root_resolved in candidate.parents:
            return True
    return False


def _allow_protected_export_dirs() -> bool:
    return _bool_env("BUG_RESOLUTION_RADAR_ALLOW_PROTECTED_EXPORT_DIRS", False)


def _configured_export_path(settings: Settings) -> Path | None:
    configured = str(getattr(settings, "REPORT_PPT_DOWNLOAD_DIR", "") or "").strip()
    if not configured:
        return None
    return Path(configured).expanduser()


def _default_report_export_dir(settings: Settings) -> Path:
    """
    Pick a writable export directory with minimum-privilege defaults.

    On macOS we avoid protected user folders (Downloads/Desktop/Documents) by
    default because they may trigger consent prompts on managed endpoints.
    """
    configured = _configured_export_path(settings)
    skip_protected = sys.platform == "darwin" and not _allow_protected_export_dirs()
    candidates: list[Path] = []
    if configured is not None and not (
        skip_protected and _is_macos_protected_user_folder(configured)
    ):
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            config_home() / "exports",
        ]
    )
    if not skip_protected:
        candidates.append(Path.home() / "Downloads")

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
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


def _phase_state_key(scope_key: str) -> str:
    return f"{_REPORT_PHASE_KEY_PREFIX}::{scope_key}"


def _request_sig_state_key(scope_key: str) -> str:
    return f"{_REPORT_REQUEST_SIG_KEY_PREFIX}::{scope_key}"


def _artifact_state_key(scope_key: str) -> str:
    return f"{_REPORT_ARTIFACT_KEY_PREFIX}::{scope_key}"


def _normalize_filter_values(values: list[str]) -> list[str]:
    clean = [str(v or "").strip() for v in list(values or []) if str(v or "").strip()]
    return sorted(set(clean))


def _data_path_mtime_ns(path_like: object) -> int:
    path_text = str(path_like or "").strip()
    if not path_text:
        return 0
    try:
        return int(Path(path_text).expanduser().stat().st_mtime_ns)
    except Exception:
        return 0


def _report_request_signature(
    settings: Settings,
    *,
    country: str,
    source_id: str,
    status_filters: list[str],
    priority_filters: list[str],
    assignee_filters: list[str],
) -> str:
    payload = {
        "country": str(country or "").strip(),
        "source_id": str(source_id or "").strip(),
        "status_filters": _normalize_filter_values(status_filters),
        "priority_filters": _normalize_filter_values(priority_filters),
        "assignee_filters": _normalize_filter_values(assignee_filters),
        "analysis_lookback_months": int(getattr(settings, "ANALYSIS_LOOKBACK_MONTHS", 0) or 0),
        "data_path": str(getattr(settings, "DATA_PATH", "") or "").strip(),
        "data_mtime_ns": _data_path_mtime_ns(getattr(settings, "DATA_PATH", "")),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _clear_generated_report_state(scope_key: str) -> None:
    st.session_state.pop(_artifact_state_key(scope_key), None)
    st.session_state.pop(_request_sig_state_key(scope_key), None)
    st.session_state[_phase_state_key(scope_key)] = "idle"


def _ready_artifact(scope_key: str, *, request_sig: str) -> dict[str, object] | None:
    payload = st.session_state.get(_artifact_state_key(scope_key))
    if not isinstance(payload, dict):
        return None

    payload_sig = str(payload.get("request_sig") or "").strip()
    if payload_sig != str(request_sig or "").strip():
        return None

    content = payload.get("content")
    if not isinstance(content, (bytes, bytearray)):
        return None
    return payload


def _int_from_obj(value: object, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _bytes_from_obj(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return b""


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
        saved_path = Path(saved_path_value)
        link_label = saved_path.name or saved_path_value
        with st.container():
            if st.button(
                link_label,
                key=f"btn_open_saved_report::{scope_key}::{saved_path_value}",
                type="secondary",
                width="content",
                help=f"Abrir carpeta del informe\n{saved_path_value}",
            ):
                _reveal_in_file_manager(saved_path)


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
    phase_key = _phase_state_key(scope_key)
    request_sig_key = _request_sig_state_key(scope_key)

    export_dir = _default_report_export_dir(settings)
    export_dir_label = str(export_dir)
    configured_export_path = _configured_export_path(settings)
    if (
        configured_export_path is not None
        and sys.platform == "darwin"
        and not _allow_protected_export_dirs()
        and _is_macos_protected_user_folder(configured_export_path)
    ):
        st.caption(
            "Ruta de exportación protegida detectada en macOS. "
            f"Para evitar prompts de permisos, el guardado se redirige a: {export_dir_label}"
        )

    current_request_sig = _report_request_signature(
        settings,
        country=country,
        source_id=source_id,
        status_filters=status_filters,
        priority_filters=priority_filters,
        assignee_filters=assignee_filters,
    )

    stored_request_sig = str(st.session_state.get(request_sig_key) or "").strip()
    phase = str(st.session_state.get(phase_key) or "idle").strip().lower()
    if phase not in {"idle", "generating", "ready"}:
        phase = "idle"
        st.session_state[phase_key] = phase

    if (
        phase in {"generating", "ready"}
        and stored_request_sig
        and stored_request_sig != current_request_sig
    ):
        _clear_generated_report_state(scope_key)
        phase = "idle"
        stored_request_sig = ""

    artifact = _ready_artifact(scope_key, request_sig=current_request_sig)
    if phase == "ready" and artifact is None:
        _clear_generated_report_state(scope_key)
        phase = "idle"

    # Auto-genera el informe al entrar en la pantalla (o al cambiar scope/filtros).
    if phase == "idle" and artifact is None:
        st.session_state.pop(_saved_path_state_key(scope_key), None)
        st.session_state[request_sig_key] = current_request_sig
        st.session_state[phase_key] = "generating"
        st.session_state.pop(_artifact_state_key(scope_key), None)
        phase = "generating"
        _store_status(
            scope_key=scope_key,
            kind="info",
            message="Generación automática del informe PPT iniciada.",
        )

    status_slot = st.empty()

    saved_path_for_scope = str(st.session_state.get(_saved_path_state_key(scope_key)) or "").strip()
    save_already_done_in_visit = bool(saved_path_for_scope)
    run_save = False
    if not save_already_done_in_visit:
        run_save = st.button(
            "Guardar en disco",
            key=f"btn_save_scope_ppt::{scope_key}",
            type="primary",
            width="content",
            disabled=phase != "ready",
            help=(
                "Se habilita cuando finalice la generación automática. "
                f"Guardará el PPT en: {export_dir_label}"
            ),
        )

    if phase == "generating":
        st.caption(
            "Estado: generando informe. El botón 'Guardar en disco' se habilitará al finalizar."
        )
    elif phase == "ready" and artifact is not None:
        file_name = str(artifact.get("file_name") or "informe.pptx")
        slide_count = _int_from_obj(artifact.get("slide_count"), default=0)
        total_issues = _int_from_obj(artifact.get("total_issues"), default=0)
        st.caption(
            f"Informe listo para guardar en disco: {file_name} · "
            f"{slide_count} slides · {total_issues} issues."
        )

    if run_save:
        ready_payload = _ready_artifact(scope_key, request_sig=current_request_sig)
        if ready_payload is None:
            _store_status(
                scope_key=scope_key,
                kind="error",
                message=(
                    "El informe preparado ya no coincide con el scope/filtros actuales. "
                    "La pantalla iniciará una nueva generación automáticamente."
                ),
            )
        else:
            try:
                file_name = str(ready_payload.get("file_name") or "").strip() or "radar-export.pptx"
                content = _bytes_from_obj(ready_payload.get("content"))
                export_path = _unique_export_path(export_dir, file_name=file_name)
                export_path.write_bytes(content)
                st.session_state[_saved_path_state_key(scope_key)] = str(export_path)
                _store_status(
                    scope_key=scope_key,
                    kind="success",
                    message=(
                        "Guardado manual completado. "
                        "Archivo guardado en el enlace mostrado a continuación."
                    ),
                )
                st.rerun()
            except Exception as exc:
                _store_status(
                    scope_key=scope_key,
                    kind="error",
                    message=f"No se pudo completar el guardado manual del informe PPT: {exc}",
                )

    if str(st.session_state.get(phase_key) or "").strip().lower() == "generating":
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
                    include_kpis=False,
                    include_timeseries_chart=False,
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

                st.session_state[_artifact_state_key(scope_key)] = {
                    "request_sig": current_request_sig,
                    "file_name": str(result.file_name or "radar-export.pptx"),
                    "content": bytes(result.content or b""),
                    "slide_count": int(result.slide_count or 0),
                    "total_issues": int(result.total_issues or 0),
                    "open_issues": int(result.open_issues or 0),
                    "closed_issues": int(result.closed_issues or 0),
                }
                st.session_state[request_sig_key] = current_request_sig
                st.session_state[phase_key] = "ready"

            _store_status(
                scope_key=scope_key,
                kind="success",
                message=(
                    f"Informe generado · {result.slide_count} slides · "
                    f"{result.total_issues} issues ({result.open_issues} abiertas). "
                    "Botón 'Guardar en disco' habilitado."
                ),
            )
            st.rerun()
        except Exception as exc:
            _clear_generated_report_state(scope_key)
            _store_status(
                scope_key=scope_key,
                kind="error",
                message=f"No se pudo generar el informe PPT: {exc}",
            )

    with status_slot:
        _render_status(scope_key)
