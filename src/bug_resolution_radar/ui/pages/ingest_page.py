"""Ingestion page to trigger data collection from configured source endpoints."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple, cast

import pandas as pd
import streamlit as st

from bug_resolution_radar.common.utils import now_iso
from bug_resolution_radar.config import (
    Settings,
    helix_sources,
    jira_sources,
    save_settings,
)
from bug_resolution_radar.ingest.helix_ingest import ingest_helix
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.ui.common import load_issues_doc, save_issues_doc


@dataclass
class _IngestProgress:
    connector: str
    state: str = "idle"  # idle | running | success | partial | error
    started_at: str = ""
    finished_at: str = ""
    total_sources: int = 0
    completed_sources: int = 0
    success_count: int = 0
    messages: List[Tuple[bool, str]] = field(default_factory=list)
    summary: str = ""


_INGEST_PROGRESS_LOCK = threading.Lock()
_INGEST_PROGRESS_BY_CONNECTOR: Dict[str, _IngestProgress] = {}
_HELIX_AUTO_RESUME_MAX_ATTEMPTS = 3


def _progress_entry(connector: str) -> _IngestProgress:
    entry = _INGEST_PROGRESS_BY_CONNECTOR.get(connector)
    if entry is not None:
        return entry
    fresh = _IngestProgress(connector=str(connector or "").strip().lower())
    _INGEST_PROGRESS_BY_CONNECTOR[fresh.connector] = fresh
    return fresh


def _progress_start(connector: str, *, total_sources: int) -> bool:
    key = str(connector or "").strip().lower()
    with _INGEST_PROGRESS_LOCK:
        entry = _progress_entry(key)
        if entry.state == "running":
            return False
        entry.state = "running"
        entry.started_at = now_iso()
        entry.finished_at = ""
        entry.total_sources = max(0, int(total_sources))
        entry.completed_sources = 0
        entry.success_count = 0
        entry.messages = []
        entry.summary = ""
        return True


def _progress_append_message(
    connector: str,
    *,
    ok: bool,
    msg: str,
    count_source: bool = True,
) -> None:
    key = str(connector or "").strip().lower()
    with _INGEST_PROGRESS_LOCK:
        entry = _progress_entry(key)
        entry.messages.append((bool(ok), str(msg or "").strip()))
        if count_source:
            entry.completed_sources = max(0, int(entry.completed_sources) + 1)
        if ok:
            entry.success_count = max(0, int(entry.success_count) + 1)


def _progress_finish(connector: str, *, state: str, summary: str) -> None:
    key = str(connector or "").strip().lower()
    with _INGEST_PROGRESS_LOCK:
        entry = _progress_entry(key)
        entry.state = str(state or "error").strip().lower()
        entry.finished_at = now_iso()
        entry.summary = str(summary or "").strip()
        if entry.total_sources > 0:
            entry.completed_sources = min(max(0, entry.completed_sources), int(entry.total_sources))


def _progress_snapshot(connector: str) -> Dict[str, Any]:
    key = str(connector or "").strip().lower()
    with _INGEST_PROGRESS_LOCK:
        entry = _progress_entry(key)
        return {
            "connector": entry.connector,
            "state": entry.state,
            "started_at": entry.started_at,
            "finished_at": entry.finished_at,
            "total_sources": int(entry.total_sources),
            "completed_sources": int(entry.completed_sources),
            "success_count": int(entry.success_count),
            "messages": list(entry.messages),
            "summary": entry.summary,
        }


def _source_label(source: Dict[str, str], *, fallback: str) -> str:
    country = str(source.get("country", "")).strip()
    alias = str(source.get("alias", "")).strip()
    if country and alias:
        return f"{country} · {alias}"
    if alias:
        return f"{fallback} · {alias}"
    return fallback


def _pick_test_source(selected_sources: List[Dict[str, str]]) -> Dict[str, str] | None:
    if not selected_sources:
        return None
    # Keep tests fast: use only the first selected source.
    return dict(selected_sources[0])


def _is_retryable_helix_failure(message: str) -> bool:
    txt = str(message or "").strip().lower()
    if not txt:
        return False
    retryable_tokens = (
        "timeout",
        "tiempo máximo",
        "reintentos agotados",
        "demasiadas páginas",
    )
    return any(token in txt for token in retryable_tokens)


def _render_progress_status(
    *,
    connector: str,
    title: str,
) -> bool:
    snapshot = _progress_snapshot(connector)
    state = str(snapshot.get("state") or "idle").strip().lower()
    if state == "idle":
        return False

    total = int(snapshot.get("total_sources") or 0)
    completed = int(snapshot.get("completed_sources") or 0)
    success_count = int(snapshot.get("success_count") or 0)
    messages = cast(List[Tuple[bool, str]], snapshot.get("messages") or [])

    if state == "running":
        with st.status(f"{title}: ingesta en curso", state="running", expanded=True):
            st.caption(f"Progreso: {completed}/{total} fuentes finalizadas.")
            for ok, msg in messages:
                (st.success if ok else st.error)(msg)
        return True

    ui_state: Literal["complete", "error"] = (
        "complete" if state in {"success", "partial"} else "error"
    )
    headline = str(snapshot.get("summary") or f"{title}: ingesta finalizada.")
    with st.status(headline, state=ui_state, expanded=False):
        st.caption(f"Resultado: {success_count}/{total} fuentes OK.")
        finished_at = str(snapshot.get("finished_at") or "").strip()
        if finished_at:
            st.caption(f"Finalizada: {finished_at}")
        for ok, msg in messages:
            (st.success if ok else st.error)(msg)
    return False


def _start_jira_ingest_job(settings: Settings, *, selected_sources: List[Dict[str, str]]) -> bool:
    sources = [dict(src) for src in selected_sources]
    if not _progress_start("jira", total_sources=len(sources)):
        return False
    settings_snapshot = settings.model_copy(deep=True)

    def _worker() -> None:
        try:
            issues_doc = load_issues_doc(settings_snapshot.DATA_PATH)
            work_doc = issues_doc
            for src in sources:
                try:
                    ok, msg, new_doc = ingest_jira(
                        settings=settings_snapshot,
                        dry_run=False,
                        existing_doc=work_doc,
                        source=src,
                    )
                except Exception as e:
                    ok = False
                    msg = (
                        f"{_source_label(src, fallback='Jira')}: error inesperado en ingesta Jira "
                        f"({type(e).__name__}): {e}"
                    )
                    new_doc = None
                if ok and new_doc is not None:
                    work_doc = new_doc
                _progress_append_message("jira", ok=ok, msg=msg, count_source=True)

            snap = _progress_snapshot("jira")
            success_count = int(snap.get("success_count") or 0)
            total_sources = max(1, len(sources))
            if success_count <= 0:
                _progress_finish(
                    "jira",
                    state="error",
                    summary="No se pudo ingestar ninguna fuente Jira.",
                )
                return

            try:
                save_issues_doc(settings_snapshot.DATA_PATH, work_doc)
            except Exception as e:
                _progress_append_message(
                    "jira",
                    ok=False,
                    msg=(f"Error guardando resultados Jira: {type(e).__name__}: {e}"),
                    count_source=False,
                )
                _progress_finish(
                    "jira",
                    state="error" if success_count == 0 else "partial",
                    summary="Reingesta Jira finalizada con error al guardar resultados.",
                )
                return

            _progress_finish(
                "jira",
                state="success" if success_count == total_sources else "partial",
                summary=(
                    f"Reingesta Jira finalizada: {success_count}/{total_sources} fuentes OK. "
                    f"Guardado en {settings_snapshot.DATA_PATH}."
                ),
            )
        except Exception as e:
            _progress_append_message(
                "jira",
                ok=False,
                msg=f"Error inesperado de orquestación Jira ({type(e).__name__}): {e}",
                count_source=False,
            )
            _progress_finish(
                "jira",
                state="error",
                summary="La ingesta Jira terminó con error.",
            )

    threading.Thread(target=_worker, name="jira-ingest-worker", daemon=True).start()
    return True


def _start_helix_ingest_job(settings: Settings, *, selected_sources: List[Dict[str, str]]) -> bool:
    sources = [dict(src) for src in selected_sources]
    if not _progress_start("helix", total_sources=len(sources)):
        return False
    settings_snapshot = settings.model_copy(deep=True)

    def _worker() -> None:
        try:
            helix_path = _get_helix_path(settings_snapshot)
            helix_repo = HelixRepo(Path(helix_path))
            stored_helix_doc = helix_repo.load() or HelixDocument.empty()
            merged_helix = stored_helix_doc
            issues_doc = load_issues_doc(settings_snapshot.DATA_PATH)
            has_partial_updates = False
            helix_browser = (
                str(getattr(settings_snapshot, "HELIX_BROWSER", "chrome") or "chrome").strip()
                or "chrome"
            )
            helix_proxy = str(getattr(settings_snapshot, "HELIX_PROXY", "") or "").strip()
            helix_ssl_verify = str(getattr(settings_snapshot, "HELIX_SSL_VERIFY", "") or "").strip()

            for src in sources:
                source_label = _source_label(src, fallback="Helix")
                attempt = 0
                final_ok = False
                final_msg = f"{source_label}: no se pudo completar la ingesta."

                while attempt < _HELIX_AUTO_RESUME_MAX_ATTEMPTS:
                    attempt += 1
                    try:
                        ok, msg, new_helix_doc = ingest_helix(
                            browser=helix_browser,
                            country=str(src.get("country", "")).strip(),
                            source_alias=str(src.get("alias", "")).strip(),
                            source_id=str(src.get("source_id", "")).strip(),
                            proxy=helix_proxy,
                            ssl_verify=helix_ssl_verify,
                            service_origin_buug=src.get("service_origin_buug"),
                            service_origin_n1=src.get("service_origin_n1"),
                            service_origin_n2=src.get("service_origin_n2"),
                            dry_run=False,
                            existing_doc=HelixDocument.empty(),
                            cache_doc=merged_helix,
                        )
                    except Exception as e:
                        ok = False
                        msg = (
                            f"{source_label}: error inesperado en ingesta Helix "
                            f"({type(e).__name__}): {e}"
                        )
                        new_helix_doc = None

                    if new_helix_doc is not None and new_helix_doc.items:
                        has_partial_updates = True
                        merged_helix = _merge_helix_items(merged_helix, new_helix_doc.items)
                        merged_helix.ingested_at = new_helix_doc.ingested_at
                        merged_helix.helix_base_url = new_helix_doc.helix_base_url
                        merged_helix.query = "multi-source"
                        mapped = [_helix_item_to_issue(it) for it in new_helix_doc.items]
                        issues_doc = _merge_issues(issues_doc, mapped)

                    if ok:
                        final_ok = True
                        final_msg = msg
                        if attempt > 1:
                            final_msg = (
                                f"{final_msg} Reintento automático OK "
                                f"({attempt}/{_HELIX_AUTO_RESUME_MAX_ATTEMPTS})."
                            )
                        break

                    final_msg = msg
                    retryable_failure = _is_retryable_helix_failure(msg)
                    if retryable_failure and attempt < _HELIX_AUTO_RESUME_MAX_ATTEMPTS:
                        _progress_append_message(
                            "helix",
                            ok=False,
                            msg=(
                                f"{msg} Reintentando automáticamente desde cache local "
                                f"({attempt + 1}/{_HELIX_AUTO_RESUME_MAX_ATTEMPTS})."
                            ),
                            count_source=False,
                        )
                        continue
                    break

                _progress_append_message("helix", ok=final_ok, msg=final_msg, count_source=True)

            snap = _progress_snapshot("helix")
            success_count = int(snap.get("success_count") or 0)
            total_sources = max(1, len(sources))
            if success_count <= 0:
                if has_partial_updates:
                    try:
                        issues_doc.ingested_at = now_iso()
                        helix_repo.save(merged_helix)
                        save_issues_doc(settings_snapshot.DATA_PATH, issues_doc)
                        _progress_append_message(
                            "helix",
                            ok=False,
                            msg=(
                                "Se guardó avance parcial de Helix en cache local para "
                                "continuar automáticamente en la siguiente ingesta."
                            ),
                            count_source=False,
                        )
                    except Exception as e:
                        _progress_append_message(
                            "helix",
                            ok=False,
                            msg=(
                                "No se pudo guardar avance parcial de Helix: "
                                f"{type(e).__name__}: {e}"
                            ),
                            count_source=False,
                        )
                _progress_finish(
                    "helix",
                    state="error",
                    summary="No se pudo ingestar ninguna fuente Helix.",
                )
                return

            try:
                issues_doc.ingested_at = now_iso()
                helix_repo.save(merged_helix)
                save_issues_doc(settings_snapshot.DATA_PATH, issues_doc)
            except Exception as e:
                _progress_append_message(
                    "helix",
                    ok=False,
                    msg=(f"Error guardando resultados Helix: {type(e).__name__}: {e}"),
                    count_source=False,
                )
                _progress_finish(
                    "helix",
                    state="error" if success_count == 0 else "partial",
                    summary="Reingesta Helix finalizada con error al guardar resultados.",
                )
                return

            _progress_finish(
                "helix",
                state="success" if success_count == total_sources else "partial",
                summary=(
                    f"Reingesta Helix finalizada: {success_count}/{total_sources} fuentes OK. "
                    f"Guardado en {helix_path} y {settings_snapshot.DATA_PATH}."
                ),
            )
        except Exception as e:
            _progress_append_message(
                "helix",
                ok=False,
                msg=f"Error inesperado de orquestación Helix ({type(e).__name__}): {e}",
                count_source=False,
            )
            _progress_finish(
                "helix",
                state="error",
                summary="La ingesta Helix terminó con error.",
            )

    threading.Thread(target=_worker, name="helix-ingest-worker", daemon=True).start()
    return True


def _get_helix_path(settings: Settings) -> str:
    p = (getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return p or "data/helix.json"


def _issue_merge_key(issue: NormalizedIssue) -> str:
    sid = str(issue.source_id or "").strip().lower()
    key = str(issue.key or "").strip().upper()
    if sid:
        return f"{sid}::{key}"
    return key


def _merge_issues(doc: IssuesDocument, incoming: List[NormalizedIssue]) -> IssuesDocument:
    merged: Dict[str, NormalizedIssue] = {_issue_merge_key(i): i for i in doc.issues}
    for issue in incoming:
        merged[_issue_merge_key(issue)] = issue
    doc.issues = list(merged.values())
    return doc


def _helix_merge_key(item: HelixWorkItem) -> str:
    sid = str(item.source_id or "").strip().lower()
    item_id = str(item.id or "").strip().upper()
    if sid:
        return f"{sid}::{item_id}"
    return item_id


def _merge_helix_items(doc: HelixDocument, incoming: List[HelixWorkItem]) -> HelixDocument:
    merged: Dict[str, HelixWorkItem] = {_helix_merge_key(i): i for i in doc.items}
    for item in incoming:
        merged[_helix_merge_key(item)] = item
    doc.items = list(merged.values())
    return doc


def _is_closed_status(value: str) -> bool:
    token = (value or "").strip().lower()
    return token in {
        "closed",
        "resolved",
        "done",
        "deployed",
        "accepted",
        "cancelled",
        "canceled",
    }


def _helix_item_to_issue(item: HelixWorkItem) -> NormalizedIssue:
    status = str(item.status or "").strip() or "Open"
    created = (
        str(item.start_datetime or item.target_date or item.last_modified or "").strip() or None
    )
    updated = (
        str(item.last_modified or item.closed_date or item.start_datetime or "").strip() or None
    )
    closed_date = str(item.closed_date or "").strip() or None
    resolved = closed_date or (updated if _is_closed_status(status) else None)
    label = (
        f"{str(item.matrix_service_n1 or '').strip()} {str(item.source_service_n1 or '').strip()}"
    ).strip()
    impacted = str(item.impacted_service or item.service or "").strip()
    components = [impacted] if impacted else []
    return NormalizedIssue(
        key=str(item.id or "").strip(),
        summary=str(item.summary or "").strip(),
        status=status,
        type=str(item.incident_type or "").strip() or "Helix",
        priority=str(item.priority or "").strip(),
        created=created,
        updated=updated,
        resolved=resolved,
        assignee=str(item.assignee or "").strip(),
        reporter=str(item.customer_name or "").strip(),
        labels=[label] if label else [],
        components=components,
        resolution="",
        resolution_type="",
        url=str(item.url or "").strip(),
        country=str(item.country or "").strip(),
        source_type="helix",
        source_alias=str(item.source_alias or "").strip(),
        source_id=str(item.source_id or "").strip(),
    )


def _render_sources_preview(rows: List[Dict[str, str]], cols: List[str]) -> None:
    if not rows:
        st.info("No hay orígenes configurados.")
        return
    frame = pd.DataFrame([{c: r.get(c, "") for c in cols} for r in rows])
    st.dataframe(frame, width="stretch", hide_index=True)


def _render_batch_messages(messages: List[Tuple[bool, str]]) -> None:
    for ok, msg in messages:
        (st.success if ok else st.error)(msg)


def _jira_last_ingest_payload(
    issues_doc: IssuesDocument,
    *,
    reset_display: bool,
) -> Dict[str, Any]:
    if reset_display:
        return {
            "schema_version": issues_doc.schema_version,
            "ingested_at": "",
            "jira_base_url": "",
            "query": "",
            "jira_source_count": 0,
            "issues_count": 0,
        }

    jira_source_ids = {
        str(i.source_id or "").strip()
        for i in issues_doc.issues
        if str(i.source_type or "").strip().lower() == "jira"
    }
    return {
        "schema_version": issues_doc.schema_version,
        "ingested_at": issues_doc.ingested_at,
        "jira_base_url": issues_doc.jira_base_url,
        "query": issues_doc.query,
        "jira_source_count": len([s for s in jira_source_ids if s]),
        "issues_count": len(issues_doc.issues),
    }


def _helix_last_ingest_payload(
    stored_helix_doc: HelixDocument,
    *,
    helix_path: str,
    reset_display: bool,
) -> Dict[str, Any]:
    if reset_display:
        return {
            "schema_version": stored_helix_doc.schema_version,
            "ingested_at": "",
            "helix_base_url": "",
            "query": "",
            "helix_source_count": 0,
            "items_count": 0,
            "data_path": helix_path,
        }

    helix_source_ids = {str(i.source_id or "").strip() for i in stored_helix_doc.items}
    return {
        "schema_version": stored_helix_doc.schema_version,
        "ingested_at": stored_helix_doc.ingested_at,
        "helix_base_url": stored_helix_doc.helix_base_url,
        "query": stored_helix_doc.query,
        "helix_source_count": len([s for s in helix_source_ids if s]),
        "items_count": len(stored_helix_doc.items),
        "data_path": helix_path,
    }


def _parse_json_str_list(raw: object) -> List[str]:
    txt = str(raw or "").strip()
    if not txt:
        return []
    try:
        payload = json.loads(txt)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    out: List[str] = []
    for item in payload:
        sid = str(item or "").strip()
        if sid and sid not in out:
            out.append(sid)
    return out


def _persist_jira_ingest_disabled_sources(
    settings: Settings, disabled_source_ids: List[str]
) -> Settings:
    normalized = [str(x).strip() for x in disabled_source_ids if str(x).strip()]
    new_settings = settings.model_copy(
        update={
            "JIRA_INGEST_DISABLED_SOURCES_JSON": json.dumps(
                normalized, ensure_ascii=False, separators=(",", ":")
            )
        }
    )
    save_settings(new_settings)
    return new_settings


def _persist_helix_ingest_disabled_sources(
    settings: Settings, disabled_source_ids: List[str]
) -> Settings:
    normalized = [str(x).strip() for x in disabled_source_ids if str(x).strip()]
    new_settings = settings.model_copy(
        update={
            "HELIX_INGEST_DISABLED_SOURCES_JSON": json.dumps(
                normalized, ensure_ascii=False, separators=(",", ":")
            )
        }
    )
    save_settings(new_settings)
    return new_settings


def render(settings: Settings) -> None:
    # Avoid emoji icons in tab labels: some environments render them as empty squares.
    running_any = False
    t_jira, t_helix = st.tabs(["Jira", "Helix"])

    with t_jira:
        jira_cfg = jira_sources(settings)
        st.caption(f"Fuentes Jira configuradas: {len(jira_cfg)}")
        valid_jira_source_ids = [
            str(src.get("source_id", "")).strip()
            for src in jira_cfg
            if str(src.get("source_id", "")).strip()
        ]
        disabled_jira_source_ids = [
            sid
            for sid in _parse_json_str_list(
                getattr(settings, "JIRA_INGEST_DISABLED_SOURCES_JSON", "")
            )
            if sid in valid_jira_source_ids
        ]
        disabled_jira_set = set(disabled_jira_source_ids)

        if jira_cfg:
            jira_selector_df = pd.DataFrame(
                [
                    {
                        "__ingest__": str(src.get("source_id", "")).strip()
                        not in disabled_jira_set,
                        "__source_id__": str(src.get("source_id", "")).strip(),
                        "country": str(src.get("country", "")).strip(),
                        "alias": str(src.get("alias", "")).strip(),
                        "jql": str(src.get("jql", "")).strip(),
                    }
                    for src in jira_cfg
                ]
            )
            st.markdown("### Fuentes Jira a ingestar")
            st.caption(
                "Por defecto todas marcadas. Este selector se guarda automáticamente en el .env."
            )
            jira_selector = st.data_editor(
                jira_selector_df,
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                key="ingest_jira_sources_selector",
                column_order=["__ingest__", "country", "alias", "jql"],
                disabled=["__source_id__", "country", "alias", "jql"],
                column_config={
                    "__ingest__": st.column_config.CheckboxColumn("Ingestar"),
                    "country": st.column_config.TextColumn("country"),
                    "alias": st.column_config.TextColumn("alias"),
                    "jql": st.column_config.TextColumn("jql"),
                },
            )
            selected_jira_source_ids = {
                str(row.get("__source_id__", "")).strip()
                for row in jira_selector.to_dict(orient="records")
                if bool(row.get("__ingest__", False)) and str(row.get("__source_id__", "")).strip()
            }
            new_disabled_jira_source_ids = [
                sid for sid in valid_jira_source_ids if sid not in selected_jira_source_ids
            ]
            if new_disabled_jira_source_ids != disabled_jira_source_ids:
                settings = _persist_jira_ingest_disabled_sources(
                    settings, new_disabled_jira_source_ids
                )
                disabled_jira_source_ids = new_disabled_jira_source_ids
            jira_cfg_selected = [
                src
                for src in jira_cfg
                if str(src.get("source_id", "")).strip() not in set(disabled_jira_source_ids)
            ]
            st.caption(f"Seleccionadas para ingesta Jira: {len(jira_cfg_selected)}/{len(jira_cfg)}")
        else:
            jira_cfg_selected = []
            _render_sources_preview(jira_cfg, ["country", "alias", "jql"])

        jira_running = (
            str(_progress_snapshot("jira").get("state") or "").strip().lower() == "running"
        )

        col_a, col_b = st.columns(2)
        with col_a:
            test_jira = st.button("Test Jira", key="btn_test_jira_all", disabled=jira_running)
        with col_b:
            run_jira = st.button(
                "Reingestar Jira",
                key="btn_run_jira_all",
                disabled=jira_running,
            )

        issues_doc = load_issues_doc(settings.DATA_PATH)

        if test_jira:
            if not jira_cfg:
                st.error("No hay fuentes Jira configuradas.")
            elif not jira_cfg_selected:
                st.warning(
                    "Selecciona al menos una fuente Jira para poder hacer el test de conectividad."
                )
            else:
                test_source = _pick_test_source(jira_cfg_selected)
                if test_source is None:
                    st.warning(
                        "Selecciona al menos una fuente Jira para poder hacer el test de conectividad."
                    )
                else:
                    with st.spinner("Probando una fuente Jira seleccionada..."):
                        ok, msg, _ = ingest_jira(
                            settings=settings,
                            dry_run=True,
                            source=test_source,
                        )
                    _render_batch_messages([(ok, msg)])

        if run_jira:
            if not jira_cfg:
                st.error("No hay fuentes Jira configuradas.")
            elif not jira_cfg_selected:
                st.warning("No hay fuentes Jira seleccionadas para ingesta.")
            else:
                if _start_jira_ingest_job(settings, selected_sources=jira_cfg_selected):
                    st.rerun()
                else:
                    st.warning("Ya hay una ingesta Jira en curso.")

        jira_running = _render_progress_status(connector="jira", title="Jira")
        running_any = running_any or jira_running

        st.markdown("### Última ingesta (Jira)")
        if jira_running:
            st.caption(
                "Nueva ingesta Jira en curso: se limpiaron los resultados de la ingesta previa."
            )
        st.json(_jira_last_ingest_payload(issues_doc, reset_display=jira_running))

    with t_helix:
        helix_cfg = helix_sources(settings)
        st.caption(f"Fuentes Helix configuradas: {len(helix_cfg)}")
        valid_helix_source_ids = [
            str(src.get("source_id", "")).strip()
            for src in helix_cfg
            if str(src.get("source_id", "")).strip()
        ]
        disabled_helix_source_ids = [
            sid
            for sid in _parse_json_str_list(
                getattr(settings, "HELIX_INGEST_DISABLED_SOURCES_JSON", "")
            )
            if sid in valid_helix_source_ids
        ]
        disabled_set = set(disabled_helix_source_ids)

        if helix_cfg:
            selector_df = pd.DataFrame(
                [
                    {
                        "__ingest__": str(src.get("source_id", "")).strip() not in disabled_set,
                        "__source_id__": str(src.get("source_id", "")).strip(),
                        "country": str(src.get("country", "")).strip(),
                        "alias": str(src.get("alias", "")).strip(),
                        "service_origin_buug": str(src.get("service_origin_buug", "")).strip(),
                        "service_origin_n1": str(src.get("service_origin_n1", "")).strip(),
                        "service_origin_n2": str(src.get("service_origin_n2", "")).strip(),
                    }
                    for src in helix_cfg
                ]
            )
            st.markdown("### Fuentes Helix a ingestar")
            st.caption(
                "Por defecto todas marcadas. Este selector se guarda automáticamente en el .env."
            )
            helix_selector = st.data_editor(
                selector_df,
                hide_index=True,
                num_rows="fixed",
                width="stretch",
                key="ingest_helix_sources_selector",
                column_order=[
                    "__ingest__",
                    "country",
                    "alias",
                    "service_origin_buug",
                    "service_origin_n1",
                    "service_origin_n2",
                ],
                disabled=[
                    "__source_id__",
                    "country",
                    "alias",
                    "service_origin_buug",
                    "service_origin_n1",
                    "service_origin_n2",
                ],
                column_config={
                    "__ingest__": st.column_config.CheckboxColumn("Ingestar"),
                    "country": st.column_config.TextColumn("country"),
                    "alias": st.column_config.TextColumn("alias"),
                    "service_origin_buug": st.column_config.TextColumn("Servicio Origen BU/UG"),
                    "service_origin_n1": st.column_config.TextColumn("Servicio Origen N1"),
                    "service_origin_n2": st.column_config.TextColumn("Servicio Origen N2"),
                },
            )
            selected_helix_source_ids = {
                str(row.get("__source_id__", "")).strip()
                for row in helix_selector.to_dict(orient="records")
                if bool(row.get("__ingest__", False)) and str(row.get("__source_id__", "")).strip()
            }
            new_disabled_helix_source_ids = [
                sid for sid in valid_helix_source_ids if sid not in selected_helix_source_ids
            ]
            if new_disabled_helix_source_ids != disabled_helix_source_ids:
                settings = _persist_helix_ingest_disabled_sources(
                    settings, new_disabled_helix_source_ids
                )
                disabled_helix_source_ids = new_disabled_helix_source_ids
            helix_cfg_selected = [
                src
                for src in helix_cfg
                if str(src.get("source_id", "")).strip() not in set(disabled_helix_source_ids)
            ]
            st.caption(
                f"Seleccionadas para ingesta Helix: {len(helix_cfg_selected)}/{len(helix_cfg)}"
            )
        else:
            helix_cfg_selected = []
            _render_sources_preview(
                helix_cfg,
                [
                    "country",
                    "alias",
                    "service_origin_buug",
                    "service_origin_n1",
                    "service_origin_n2",
                ],
            )

        helix_path = _get_helix_path(settings)
        helix_repo = HelixRepo(Path(helix_path))
        stored_helix_doc = helix_repo.load() or HelixDocument.empty()
        helix_running = (
            str(_progress_snapshot("helix").get("state") or "").strip().lower() == "running"
        )
        helix_browser = (
            str(getattr(settings, "HELIX_BROWSER", "chrome") or "chrome").strip() or "chrome"
        )
        helix_proxy = str(getattr(settings, "HELIX_PROXY", "") or "").strip()
        helix_ssl_verify = str(getattr(settings, "HELIX_SSL_VERIFY", "") or "").strip()

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            test_helix = st.button(
                "Test Helix",
                key="btn_test_helix_all",
                disabled=helix_running,
            )
        with col_h2:
            run_helix = st.button(
                "Reingestar Helix",
                key="btn_run_helix_all",
                disabled=helix_running,
            )

        if test_helix:
            if not helix_cfg:
                st.error("No hay fuentes Helix configuradas.")
            elif not helix_cfg_selected:
                st.warning(
                    "Selecciona al menos una fuente Helix para poder hacer el test de conectividad."
                )
            else:
                test_source = _pick_test_source(helix_cfg_selected)
                if test_source is None:
                    st.warning(
                        "Selecciona al menos una fuente Helix para poder hacer el test de conectividad."
                    )
                else:
                    with st.spinner("Probando una fuente Helix seleccionada..."):
                        ok, msg, _ = ingest_helix(
                            browser=helix_browser,
                            country=str(test_source.get("country", "")).strip(),
                            source_alias=str(test_source.get("alias", "")).strip(),
                            source_id=str(test_source.get("source_id", "")).strip(),
                            proxy=helix_proxy,
                            ssl_verify=helix_ssl_verify,
                            service_origin_buug=test_source.get("service_origin_buug"),
                            service_origin_n1=test_source.get("service_origin_n1"),
                            service_origin_n2=test_source.get("service_origin_n2"),
                            dry_run=True,
                            existing_doc=HelixDocument.empty(),
                        )
                    _render_batch_messages([(ok, msg)])

        if run_helix:
            if not helix_cfg:
                st.error("No hay fuentes Helix configuradas.")
            elif not helix_cfg_selected:
                st.warning("No hay fuentes Helix seleccionadas para ingesta.")
            else:
                if _start_helix_ingest_job(settings, selected_sources=helix_cfg_selected):
                    st.rerun()
                else:
                    st.warning("Ya hay una ingesta Helix en curso.")

        helix_running = _render_progress_status(connector="helix", title="Helix")
        running_any = running_any or helix_running

        st.markdown("### Última ingesta (Helix)")
        if helix_running:
            st.caption(
                "Nueva ingesta Helix en curso: se limpiaron los resultados de la ingesta previa."
            )
        st.json(
            _helix_last_ingest_payload(
                stored_helix_doc,
                helix_path=helix_path,
                reset_display=helix_running,
            )
        )

    if running_any:
        # Keep ingest page state live while background jobs progress.
        time.sleep(1.0)
        st.rerun()
