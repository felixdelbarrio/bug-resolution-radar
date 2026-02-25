"""Ingestion page to trigger data collection from configured source endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings, helix_sources, jira_sources
from bug_resolution_radar.ingest.helix_ingest import ingest_helix
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.ui.common import load_issues_doc, save_issues_doc
from bug_resolution_radar.common.utils import now_iso


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
        f"{str(item.matrix_service_n1 or '').strip()} "
        f"{str(item.source_service_n1 or '').strip()}"
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


def render(settings: Settings) -> None:
    # Avoid emoji icons in tab labels: some environments render them as empty squares.
    t_jira, t_helix = st.tabs(["Jira", "Helix"])

    with t_jira:
        jira_cfg = jira_sources(settings)
        st.caption(f"Fuentes Jira configuradas: {len(jira_cfg)}")
        _render_sources_preview(jira_cfg, ["country", "alias", "jql"])

        col_a, col_b = st.columns(2)
        with col_a:
            test_jira = st.button("🔎 Test Jira", key="btn_test_jira_all")
        with col_b:
            run_jira = st.button("⬇️ Reingestar Jira", key="btn_run_jira_all")

        issues_doc = load_issues_doc(settings.DATA_PATH)

        if test_jira:
            if not jira_cfg:
                st.error("No hay fuentes Jira configuradas.")
            else:
                messages: List[Tuple[bool, str]] = []
                with st.spinner("Probando fuentes Jira..."):
                    for src in jira_cfg:
                        ok, msg, _ = ingest_jira(settings=settings, dry_run=True, source=src)
                        messages.append((ok, msg))
                _render_batch_messages(messages)

        if run_jira:
            if not jira_cfg:
                st.error("No hay fuentes Jira configuradas.")
            else:
                messages = []
                work_doc = issues_doc
                success_count = 0
                with st.spinner("Ingestando Jira para todas las fuentes configuradas..."):
                    for src in jira_cfg:
                        ok, msg, new_doc = ingest_jira(
                            settings=settings,
                            dry_run=False,
                            existing_doc=work_doc,
                            source=src,
                        )
                        messages.append((ok, msg))
                        if ok and new_doc is not None:
                            work_doc = new_doc
                            success_count += 1

                _render_batch_messages(messages)
                if success_count > 0:
                    save_issues_doc(settings.DATA_PATH, work_doc)
                    issues_doc = work_doc
                    st.success(
                        f"Reingesta Jira finalizada: {success_count}/{len(jira_cfg)} fuentes OK. "
                        f"Guardado en {settings.DATA_PATH}."
                    )
                else:
                    st.error("No se pudo ingestar ninguna fuente Jira.")

        jira_source_ids = {
            str(i.source_id or "").strip()
            for i in issues_doc.issues
            if str(i.source_type or "").strip().lower() == "jira"
        }
        st.markdown("### Última ingesta (Jira)")
        st.json(
            {
                "schema_version": issues_doc.schema_version,
                "ingested_at": issues_doc.ingested_at,
                "jira_base_url": issues_doc.jira_base_url,
                "query": issues_doc.query,
                "jira_source_count": len([s for s in jira_source_ids if s]),
                "issues_count": len(issues_doc.issues),
            }
        )

    with t_helix:
        helix_cfg = helix_sources(settings)
        st.caption(f"Fuentes Helix configuradas: {len(helix_cfg)}")
        _render_sources_preview(
            helix_cfg,
            [
                "country",
                "alias",
                "base_url",
                "organization",
                "service_origin_buug",
                "service_origin_n1",
                "browser",
                "proxy",
                "ssl_verify",
            ],
        )

        helix_path = _get_helix_path(settings)
        helix_repo = HelixRepo(Path(helix_path))
        stored_helix_doc = helix_repo.load() or HelixDocument.empty()

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            test_helix = st.button("🔎 Test Helix", key="btn_test_helix_all")
        with col_h2:
            run_helix = st.button("⬇️ Reingestar Helix", key="btn_run_helix_all")

        if test_helix:
            if not helix_cfg:
                st.error("No hay fuentes Helix configuradas.")
            else:
                messages = []
                with st.spinner("Probando fuentes Helix..."):
                    for src in helix_cfg:
                        ok, msg, _ = ingest_helix(
                            helix_base_url=str(src.get("base_url", "")).strip(),
                            browser=str(src.get("browser", "chrome")).strip(),
                            organization=str(src.get("organization", "")).strip(),
                            country=str(src.get("country", "")).strip(),
                            source_alias=str(src.get("alias", "")).strip(),
                            source_id=str(src.get("source_id", "")).strip(),
                            proxy=str(src.get("proxy", "")).strip(),
                            ssl_verify=str(src.get("ssl_verify", "true")).strip(),
                            service_origin_buug=src.get("service_origin_buug"),
                            service_origin_n1=src.get("service_origin_n1"),
                            dry_run=True,
                            existing_doc=HelixDocument.empty(),
                        )
                        messages.append((ok, msg))
                _render_batch_messages(messages)

        if run_helix:
            if not helix_cfg:
                st.error("No hay fuentes Helix configuradas.")
            else:
                messages = []
                success_count = 0
                merged_helix = stored_helix_doc
                issues_doc = load_issues_doc(settings.DATA_PATH)
                with st.spinner("Ingestando Helix para todas las fuentes configuradas..."):
                    for src in helix_cfg:
                        ok, msg, new_helix_doc = ingest_helix(
                            helix_base_url=str(src.get("base_url", "")).strip(),
                            browser=str(src.get("browser", "chrome")).strip(),
                            organization=str(src.get("organization", "")).strip(),
                            country=str(src.get("country", "")).strip(),
                            source_alias=str(src.get("alias", "")).strip(),
                            source_id=str(src.get("source_id", "")).strip(),
                            proxy=str(src.get("proxy", "")).strip(),
                            ssl_verify=str(src.get("ssl_verify", "true")).strip(),
                            service_origin_buug=src.get("service_origin_buug"),
                            service_origin_n1=src.get("service_origin_n1"),
                            dry_run=False,
                            existing_doc=HelixDocument.empty(),
                        )
                        messages.append((ok, msg))
                        if ok and new_helix_doc is not None:
                            success_count += 1
                            merged_helix = _merge_helix_items(merged_helix, new_helix_doc.items)
                            merged_helix.ingested_at = new_helix_doc.ingested_at
                            merged_helix.helix_base_url = new_helix_doc.helix_base_url
                            merged_helix.query = "multi-source"
                            mapped = [_helix_item_to_issue(it) for it in new_helix_doc.items]
                            issues_doc = _merge_issues(issues_doc, mapped)

                _render_batch_messages(messages)
                if success_count > 0:
                    issues_doc.ingested_at = now_iso()
                    helix_repo.save(merged_helix)
                    save_issues_doc(settings.DATA_PATH, issues_doc)
                    stored_helix_doc = merged_helix
                    st.success(
                        f"Reingesta Helix finalizada: {success_count}/{len(helix_cfg)} fuentes OK. "
                        f"Guardado en {helix_path} y {settings.DATA_PATH}."
                    )
                else:
                    st.error("No se pudo ingestar ninguna fuente Helix.")

        helix_source_ids = {str(i.source_id or "").strip() for i in stored_helix_doc.items}
        st.markdown("### Última ingesta (Helix)")
        st.json(
            {
                "schema_version": stored_helix_doc.schema_version,
                "ingested_at": stored_helix_doc.ingested_at,
                "helix_base_url": stored_helix_doc.helix_base_url,
                "query": stored_helix_doc.query,
                "helix_source_count": len([s for s in helix_source_ids if s]),
                "items_count": len(stored_helix_doc.items),
                "data_path": helix_path,
            }
        )
