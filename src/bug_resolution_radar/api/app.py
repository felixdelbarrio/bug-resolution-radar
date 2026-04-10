"""FastAPI application serving backend contracts and the bundled React app."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bug_resolution_radar.analytics.analysis_window import apply_analysis_depth_filter
from bug_resolution_radar.analytics.filtering import FilterState, normalize_filter_tokens
from bug_resolution_radar.analytics.issues import normalize_text_col
from bug_resolution_radar.analytics.quincenal_scope import (
    QUINCENAL_SCOPE_ALL,
    quincenal_scope_options,
)
from bug_resolution_radar.config import (
    Settings,
    all_configured_sources,
    country_rollup_sources,
    helix_sources,
    jira_sources,
    load_settings,
    restore_env_from_example,
)
from bug_resolution_radar.ingest.helix_ingest import ingest_helix as execute_helix_ingest
from bug_resolution_radar.ingest.jira_ingest import ingest_jira as execute_jira_ingest
from bug_resolution_radar.ingest.browser_runtime import open_url_in_configured_browser
from bug_resolution_radar.models.schema_helix import HelixDocument
from bug_resolution_radar.reports.service import (
    build_report_filters,
    default_report_export_dir,
    ensure_report_export_dir,
    generate_executive_report_artifact,
    generate_period_followup_report_artifact,
    save_report_content,
)
from bug_resolution_radar.repositories.issues_store import load_issues_df
from bug_resolution_radar.services.dashboard_snapshot import (
    DashboardQuery,
    build_dashboard_defaults,
    build_dashboard_snapshot,
    build_intelligence_snapshot,
    build_issue_keys,
    build_issue_rows,
    build_kanban_columns,
    build_default_filters,
    build_trend_detail,
)
from bug_resolution_radar.services.ingest_contracts import (
    ingest_overview_payload,
    persist_ingest_selection,
)
from bug_resolution_radar.services.ingest_runner import run_helix_ingest, run_jira_ingest
from bug_resolution_radar.services.notes import NotesStore
from bug_resolution_radar.services.settings_contracts import (
    load_settings_payload,
    save_settings_payload,
)
from bug_resolution_radar.services.source_maintenance import (
    cache_inventory,
    purge_source_cache,
    reset_cache_store,
    source_cache_impact,
)
from bug_resolution_radar.services.tabular_export import (
    dataframe_to_csv_bytes,
    dataframe_to_xlsx_bytes,
    download_filename,
)
from bug_resolution_radar.services.workspace import (
    WorkspaceSelection,
    available_sources_by_country,
    apply_workspace_source_scope,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _frontend_dist_dir() -> Path | None:
    candidates: list[Path] = []

    env_override = str(os.environ.get("BUG_RESOLUTION_RADAR_FRONTEND_DIST", "") or "").strip()
    if env_override:
        candidates.append(Path(env_override).expanduser())

    candidates.append(_repo_root() / "frontend" / "dist")

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "frontend_dist")

    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "frontend_dist")
        candidates.append(exe_dir.parent / "frontend_dist")
    except Exception:
        pass

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def _frontend_dev_url() -> str:
    return str(os.environ.get("BUG_RESOLUTION_RADAR_FRONTEND_DEV_URL", "") or "").strip()


def _split_csv_param(value: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in str(value or "").split(","):
        token = raw.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _json_list_from_settings(value: object) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item).strip() for item in payload if str(item).strip()]


def _workspace_query(
    *,
    country: str = "",
    source_id: str = "",
    scope_mode: str = "source",
) -> WorkspaceSelection:
    return WorkspaceSelection(
        country=str(country or "").strip(),
        source_id=str(source_id or "").strip(),
        scope_mode=str(scope_mode or "source").strip().lower() or "source",
    )


def _dashboard_query(
    *,
    country: str = "",
    source_id: str = "",
    scope_mode: str = "source",
    status: str = "",
    priority: str = "",
    assignee: str = "",
    quincenal_scope: str = QUINCENAL_SCOPE_ALL,
    issue_keys: str = "",
    issue_sort_col: str = "",
    issue_like_query: str = "",
    chart_ids: str = "",
    dark_mode: bool = False,
) -> DashboardQuery:
    return DashboardQuery(
        workspace=_workspace_query(
            country=country,
            source_id=source_id,
            scope_mode=scope_mode,
        ),
        filters=FilterState(
            status=normalize_filter_tokens(_split_csv_param(status)),
            priority=normalize_filter_tokens(_split_csv_param(priority)),
            assignee=normalize_filter_tokens(_split_csv_param(assignee)),
        ),
        quincenal_scope=str(quincenal_scope or QUINCENAL_SCOPE_ALL).strip() or QUINCENAL_SCOPE_ALL,
        issue_scope_keys=tuple(_split_csv_param(issue_keys)),
        issue_sort_col=str(issue_sort_col or "").strip(),
        issue_like_query=str(issue_like_query or "").strip(),
        chart_ids=tuple(_split_csv_param(chart_ids)),
        dark_mode=bool(dark_mode),
    )


def _select_sources(
    all_sources: Sequence[Dict[str, str]],
    *,
    requested_source_ids: Sequence[str] | None,
    disabled_source_ids: Sequence[str] | None,
) -> list[Dict[str, str]]:
    requested = {
        str(item).strip() for item in list(requested_source_ids or []) if str(item).strip()
    }
    disabled = {str(item).strip() for item in list(disabled_source_ids or []) if str(item).strip()}
    selected: list[Dict[str, str]] = []
    for source in list(all_sources or []):
        source_id = str(source.get("source_id") or "").strip()
        if not source_id or source_id in disabled:
            continue
        if requested and source_id not in requested:
            continue
        selected.append(dict(source))
    return selected


def _pick_test_source(selected_sources: Sequence[Dict[str, str]]) -> dict[str, str] | None:
    if not selected_sources:
        return None
    return dict(list(selected_sources)[0])


def _single_source_result(*, connector: str, ok: bool, message: str) -> dict[str, Any]:
    connector_label = "Jira" if str(connector).strip().lower() == "jira" else "Helix"
    return {
        "state": "success" if ok else "error",
        "summary": (f"Test {connector_label} OK." if ok else f"Test {connector_label} con error."),
        "success_count": int(bool(ok)),
        "total_sources": 1,
        "messages": [{"ok": bool(ok), "message": str(message or "").strip()}],
    }


def _scoped_dataframe_for_options(
    settings: Settings,
    *,
    workspace: WorkspaceSelection,
) -> pd.DataFrame:
    try:
        df_all = load_issues_df(settings.DATA_PATH)
    except Exception:
        return pd.DataFrame()
    if df_all.empty:
        return df_all
    scoped = apply_workspace_source_scope(df_all, settings=settings, selection=workspace)
    return apply_analysis_depth_filter(scoped, settings=settings)


def _filter_options(df: pd.DataFrame) -> dict[str, list[str]]:
    if df is None or df.empty:
        return {"status": [], "priority": [], "assignee": [], "quincenal": [QUINCENAL_SCOPE_ALL]}

    out: dict[str, list[str]] = {
        "status": [],
        "priority": [],
        "assignee": [],
        "quincenal": [QUINCENAL_SCOPE_ALL],
    }
    if "status" in df.columns:
        out["status"] = sorted(
            set(normalize_text_col(df["status"], "(sin estado)").astype(str).tolist())
        )
    if "priority" in df.columns:
        out["priority"] = sorted(
            set(normalize_text_col(df["priority"], "(sin priority)").astype(str).tolist())
        )
    if "assignee" in df.columns:
        out["assignee"] = sorted(
            set(normalize_text_col(df["assignee"], "(sin asignar)").astype(str).tolist())
        )
    return out


def _workspace_payload(
    settings: Settings,
    *,
    country: str = "",
    source_id: str = "",
    scope_mode: str = "source",
) -> dict[str, Any]:
    try:
        df_all = load_issues_df(settings.DATA_PATH)
    except Exception:
        df_all = pd.DataFrame()

    sources_by_country = (
        available_sources_by_country(settings, df_all=df_all)
        if isinstance(df_all, pd.DataFrame) and not df_all.empty
        else {}
    )
    if not sources_by_country:
        configured = all_configured_sources(settings)
        for source in configured:
            src_country = str(source.get("country") or "").strip()
            if not src_country:
                continue
            sources_by_country.setdefault(src_country, []).append(source)

    countries = list(sources_by_country.keys())
    selected_country = str(country or "").strip()
    if selected_country not in countries:
        selected_country = countries[0] if countries else ""

    country_sources = [dict(row) for row in sources_by_country.get(selected_country, [])]
    source_ids = [
        str(row.get("source_id") or "").strip()
        for row in country_sources
        if str(row.get("source_id") or "").strip()
    ]
    configured_rollup = [
        sid
        for sid in country_rollup_sources(settings).get(selected_country, [])
        if sid in source_ids
    ]
    selected_source_id = str(source_id or "").strip()
    if selected_source_id not in source_ids:
        selected_source_id = source_ids[0] if source_ids else ""
    normalized_scope_mode = str(scope_mode or "source").strip().lower() or "source"
    if normalized_scope_mode not in {"country", "source"}:
        normalized_scope_mode = "source"
    if normalized_scope_mode == "country" and not configured_rollup:
        normalized_scope_mode = "source"

    workspace = _workspace_query(
        country=selected_country,
        source_id=selected_source_id,
        scope_mode=normalized_scope_mode,
    )
    scoped_df = _scoped_dataframe_for_options(settings, workspace=workspace)
    active_source_ids = (
        [selected_source_id]
        if workspace.scope_mode == "source" and selected_source_id
        else list(configured_rollup or source_ids)
    )
    filter_options = _filter_options(scoped_df)
    filter_options["quincenal"] = list(
        quincenal_scope_options(
            scoped_df,
            settings=settings,
            country=selected_country,
            source_ids=active_source_ids,
        ).keys()
    )

    return {
        "countries": [
            {
                "country": country_name,
                "sourceCount": len(country_rows),
            }
            for country_name, country_rows in sources_by_country.items()
        ],
        "sources": country_sources,
        "selectedCountry": selected_country,
        "selectedSourceId": selected_source_id,
        "scopeMode": workspace.scope_mode,
        "hasCountryRollup": bool(configured_rollup),
        "countryRollupSourceIds": configured_rollup,
        "hasData": bool(isinstance(df_all, pd.DataFrame) and not df_all.empty),
        "filterOptions": filter_options,
    }


def _notes_store(settings: Settings) -> NotesStore:
    store = NotesStore(Path(settings.NOTES_PATH))
    store.load()
    return store


def _notes_payload(settings: Settings, *, issue_key: str = "") -> dict[str, Any]:
    store = _notes_store(settings)
    current_key = str(issue_key or "").strip()
    return {
        "issueKey": current_key,
        "note": store.get(current_key) or "",
    }


def _download_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _export_dataframe(settings: Settings, *, query: DashboardQuery) -> pd.DataFrame:
    result = build_issue_rows(
        settings,
        query=query,
        offset=0,
        limit=50000,
        sort_by=query.issue_sort_col or "updated",
        sort_dir="desc",
    )
    rows = list(result.get("rows") or [])
    return pd.DataFrame(rows)


class SourceSelectionRequest(BaseModel):
    sourceIds: list[str] = Field(default_factory=list)


class BrowserOpenRequest(BaseModel):
    url: str
    sourceType: str = "jira"
    browser: str = ""


class NoteRequest(BaseModel):
    note: str = ""


class CacheResetRequest(BaseModel):
    cacheId: str


class CachePurgeRequest(BaseModel):
    sourceId: str


class ReportRequest(BaseModel):
    country: str = ""
    sourceId: str = ""
    sourceIds: list[str] = Field(default_factory=list)
    scopeMode: str = "source"
    status: list[str] = Field(default_factory=list)
    priority: list[str] = Field(default_factory=list)
    assignee: list[str] = Field(default_factory=list)
    quincenalScope: str = QUINCENAL_SCOPE_ALL
    appliedFilterSummary: str = ""
    functionalityStatusFilters: list[str] = Field(default_factory=list)
    functionalityPriorityFilters: list[str] = Field(default_factory=list)
    functionalityFilters: list[str] = Field(default_factory=list)


class PathRevealRequest(BaseModel):
    path: str = ""


def _report_saved_payload(
    *,
    saved_path: Path,
    file_name: str,
    slide_count: int,
    total_issues: int,
    open_issues: int,
    closed_issues: int,
) -> dict[str, Any]:
    return {
        "fileName": str(file_name or "").strip(),
        "savedPath": str(saved_path),
        "savedDir": str(saved_path.parent),
        "slideCount": int(slide_count or 0),
        "totalIssues": int(total_issues or 0),
        "openIssues": int(open_issues or 0),
        "closedIssues": int(closed_issues or 0),
    }


def _reveal_in_file_manager(path: Path) -> bool:
    try:
        target_path = Path(path)
        target_dir = target_path.parent if str(target_path.parent) else Path.cwd()
        if sys.platform == "darwin":
            if target_path.exists():
                subprocess.Popen(["open", "-R", str(target_path)])
            else:
                subprocess.Popen(["open", str(target_dir)])
            return True
        if os.name == "nt":
            if target_path.exists():
                subprocess.Popen(["explorer", "/select,", str(target_path)])
            else:
                subprocess.Popen(["explorer", str(target_dir)])
            return True
        subprocess.Popen(["xdg-open", str(target_dir)])
        return True
    except Exception:
        return False


def create_app() -> FastAPI:
    app = FastAPI(title="Bug Resolution Radar API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "frontendDist": str(_frontend_dist_dir() or ""),
            "frontendDevUrl": _frontend_dev_url(),
        }

    @app.get("/api/bootstrap")
    def bootstrap(
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
    ) -> dict[str, Any]:
        settings = load_settings()
        return {
            "appTitle": str(settings.APP_TITLE or "Bug Resolution Radar"),
            "theme": str(settings.THEME or "auto"),
            "defaultFilters": build_default_filters(settings),
            "dashboardDefaults": build_dashboard_defaults(settings),
            "workspace": _workspace_payload(
                settings,
                country=country,
                source_id=sourceId,
                scope_mode=scopeMode,
            ),
            "chartsCatalog": [
                {"id": "timeseries", "label": "Evolución"},
                {"id": "age_buckets", "label": "Antigüedad"},
                {"id": "open_status_bar", "label": "Estados"},
                {"id": "open_priority_pie", "label": "Prioridades"},
                {"id": "resolution_hist", "label": "Resolución"},
            ],
            "permissionsPolicy": {
                "reports": "Solo se genera o descarga bajo acción explícita del usuario.",
                "browser": (
                    "Solo se abre navegador o se leen cookies durante acciones de "
                    "ingesta o apertura explícita."
                ),
                "filesystem": "No se escribe en disco durante renderizado o carga inicial.",
            },
        }

    @app.get("/api/workspace")
    def workspace_options(
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
    ) -> dict[str, Any]:
        settings = load_settings()
        return _workspace_payload(
            settings,
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
        )

    @app.get("/api/dashboard")
    def dashboard(
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        quincenalScope: str = QUINCENAL_SCOPE_ALL,
        issueKeys: str = "",
        issueSortCol: str = "",
        issueLikeQuery: str = "",
        chartIds: str = "",
        darkMode: bool = False,
    ) -> dict[str, Any]:
        settings = load_settings()
        query = _dashboard_query(
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
            status=status,
            priority=priority,
            assignee=assignee,
            quincenal_scope=quincenalScope,
            issue_keys=issueKeys,
            issue_sort_col=issueSortCol,
            issue_like_query=issueLikeQuery,
            chart_ids=chartIds,
            dark_mode=darkMode,
        )
        payload = build_dashboard_snapshot(settings, query=query)
        payload["workspace"] = _workspace_payload(
            settings,
            country=query.workspace.country,
            source_id=query.workspace.source_id,
            scope_mode=query.workspace.scope_mode,
        )
        return payload

    @app.get("/api/intelligence")
    def intelligence(
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        quincenalScope: str = QUINCENAL_SCOPE_ALL,
        issueKeys: str = "",
        issueSortCol: str = "",
        issueLikeQuery: str = "",
        insightsViewMode: str = "quincenal",
        insightsStatus: str = "",
        insightsPriority: str = "",
        insightsFunctionality: str = "",
        insightsStatusManual: bool = False,
        darkMode: bool = False,
    ) -> dict[str, Any]:
        settings = load_settings()
        query = _dashboard_query(
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
            status=status,
            priority=priority,
            assignee=assignee,
            quincenal_scope=quincenalScope,
            issue_keys=issueKeys,
            issue_sort_col=issueSortCol,
            issue_like_query=issueLikeQuery,
            dark_mode=darkMode,
        )
        return build_intelligence_snapshot(
            settings,
            query=query,
            insights_view_mode=insightsViewMode,
            insights_status_filters=_split_csv_param(insightsStatus),
            insights_priority_filters=_split_csv_param(insightsPriority),
            insights_functionality_filters=_split_csv_param(insightsFunctionality),
            insights_status_manual=bool(insightsStatusManual),
        )

    @app.get("/api/trends/detail")
    def trend_detail(
        chartId: str,
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        quincenalScope: str = QUINCENAL_SCOPE_ALL,
        issueKeys: str = "",
        issueSortCol: str = "",
        issueLikeQuery: str = "",
        darkMode: bool = False,
    ) -> dict[str, Any]:
        settings = load_settings()
        query = _dashboard_query(
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
            status=status,
            priority=priority,
            assignee=assignee,
            quincenal_scope=quincenalScope,
            issue_keys=issueKeys,
            issue_sort_col=issueSortCol,
            issue_like_query=issueLikeQuery,
            dark_mode=darkMode,
        )
        return build_trend_detail(settings, query=query, chart_id=chartId)

    @app.get("/api/issues")
    def issues(
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        quincenalScope: str = QUINCENAL_SCOPE_ALL,
        issueKeys: str = "",
        issueSortCol: str = "",
        issueLikeQuery: str = "",
        offset: int = 0,
        limit: int = Query(100, ge=1, le=50000),
        sortBy: str = "updated",
        sortDir: str = "desc",
    ) -> dict[str, Any]:
        settings = load_settings()
        query = _dashboard_query(
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
            status=status,
            priority=priority,
            assignee=assignee,
            quincenal_scope=quincenalScope,
            issue_keys=issueKeys,
            issue_sort_col=issueSortCol,
            issue_like_query=issueLikeQuery,
        )
        return build_issue_rows(
            settings,
            query=query,
            offset=offset,
            limit=limit,
            sort_by=sortBy,
            sort_dir=sortDir,
        )

    @app.get("/api/issues/keys")
    def issue_keys(
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        quincenalScope: str = QUINCENAL_SCOPE_ALL,
        issueKeys: str = "",
        issueSortCol: str = "",
        issueLikeQuery: str = "",
    ) -> dict[str, Any]:
        settings = load_settings()
        query = _dashboard_query(
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
            status=status,
            priority=priority,
            assignee=assignee,
            quincenal_scope=quincenalScope,
            issue_keys=issueKeys,
            issue_sort_col=issueSortCol,
            issue_like_query=issueLikeQuery,
        )
        return build_issue_keys(settings, query=query)

    @app.get("/api/issues/export")
    def issues_export(
        format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        quincenalScope: str = QUINCENAL_SCOPE_ALL,
        issueKeys: str = "",
        issueSortCol: str = "",
        issueLikeQuery: str = "",
    ) -> Response:
        settings = load_settings()
        query = _dashboard_query(
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
            status=status,
            priority=priority,
            assignee=assignee,
            quincenal_scope=quincenalScope,
            issue_keys=issueKeys,
            issue_sort_col=issueSortCol,
            issue_like_query=issueLikeQuery,
        )
        df = _export_dataframe(settings, query=query)
        if str(format).lower() == "csv":
            content = dataframe_to_csv_bytes(df, include_index=False)
            media_type = "text/csv; charset=utf-8"
            filename = download_filename("issues", ext="csv")
        else:
            content = dataframe_to_xlsx_bytes(df, sheet_name="Issues", include_index=False)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = download_filename("issues", ext="xlsx")
        return Response(content=content, media_type=media_type, headers=_download_headers(filename))

    @app.get("/api/kanban")
    def kanban(
        country: str = "",
        sourceId: str = "",
        scopeMode: str = "source",
        status: str = "",
        priority: str = "",
        assignee: str = "",
        quincenalScope: str = QUINCENAL_SCOPE_ALL,
        issueKeys: str = "",
        issueSortCol: str = "",
        issueLikeQuery: str = "",
    ) -> list[dict[str, Any]]:
        settings = load_settings()
        query = _dashboard_query(
            country=country,
            source_id=sourceId,
            scope_mode=scopeMode,
            status=status,
            priority=priority,
            assignee=assignee,
            quincenal_scope=quincenalScope,
            issue_keys=issueKeys,
            issue_sort_col=issueSortCol,
            issue_like_query=issueLikeQuery,
        )
        return build_kanban_columns(settings, query=query)

    @app.get("/api/notes/{issue_key}")
    def get_note(issue_key: str) -> dict[str, Any]:
        settings = load_settings()
        return _notes_payload(settings, issue_key=issue_key)

    @app.put("/api/notes/{issue_key}")
    def put_note(issue_key: str, payload: NoteRequest) -> dict[str, Any]:
        settings = load_settings()
        store = _notes_store(settings)
        store.set(str(issue_key or "").strip(), str(payload.note or ""))
        store.save()
        return _notes_payload(settings, issue_key=issue_key)

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return load_settings_payload()

    @app.put("/api/settings")
    def put_settings(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return save_settings_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/settings/restore-from-example")
    def restore_settings() -> dict[str, Any]:
        try:
            restored_from = restore_env_from_example()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "restoredFrom": str(restored_from),
            "settings": load_settings_payload(),
        }

    @app.get("/api/cache/inventory")
    def get_cache_inventory() -> list[dict[str, Any]]:
        settings = load_settings()
        return cache_inventory(settings)

    @app.get("/api/cache/impact")
    def get_cache_impact(sourceId: str) -> dict[str, Any]:
        settings = load_settings()
        return source_cache_impact(settings, sourceId)

    @app.post("/api/cache/reset")
    def post_cache_reset(payload: CacheResetRequest) -> dict[str, Any]:
        settings = load_settings()
        try:
            return reset_cache_store(settings, payload.cacheId)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/cache/purge-source")
    def post_cache_purge(payload: CachePurgeRequest) -> dict[str, Any]:
        settings = load_settings()
        return purge_source_cache(settings, payload.sourceId)

    @app.post("/api/browser/open")
    def browser_open(payload: BrowserOpenRequest) -> dict[str, Any]:
        settings = load_settings()
        source_type = str(payload.sourceType or "jira").strip().lower()
        target_url = str(payload.url or "").strip()
        browser = str(payload.browser or "").strip().lower()
        if not browser:
            browser = (
                str(getattr(settings, "HELIX_BROWSER", "chrome") or "chrome").strip().lower()
                if source_type == "helix"
                else str(getattr(settings, "JIRA_BROWSER", "chrome") or "chrome").strip().lower()
            )
        opened = open_url_in_configured_browser(
            target_url,
            browser,
            allow_system_default_fallback=True,
        )
        return {"opened": bool(opened), "browser": browser, "url": target_url}

    @app.get("/api/reports/export-target")
    def report_export_target() -> dict[str, Any]:
        settings = load_settings()
        export_dir = default_report_export_dir(settings)
        return {
            "directory": str(export_dir),
            "configured": bool(str(getattr(settings, "REPORT_PPT_DOWNLOAD_DIR", "") or "").strip()),
        }

    @app.post("/api/system/reveal-path")
    def reveal_path(payload: PathRevealRequest) -> dict[str, Any]:
        raw_path = str(payload.path or "").strip()
        if not raw_path:
            raise HTTPException(status_code=400, detail="No se ha recibido una ruta para abrir.")
        target = Path(raw_path).expanduser()
        return {"revealed": bool(_reveal_in_file_manager(target)), "path": str(target)}

    @app.get("/api/ingest/overview")
    def ingest_overview() -> dict[str, Any]:
        settings = load_settings()
        return ingest_overview_payload(settings)

    @app.put("/api/ingest/jira/selection")
    def put_jira_ingest_selection(payload: SourceSelectionRequest) -> dict[str, Any]:
        settings = load_settings()
        try:
            updated = persist_ingest_selection(
                settings,
                connector="jira",
                selected_source_ids=payload.sourceIds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ingest_overview_payload(updated)

    @app.put("/api/ingest/helix/selection")
    def put_helix_ingest_selection(payload: SourceSelectionRequest) -> dict[str, Any]:
        settings = load_settings()
        try:
            updated = persist_ingest_selection(
                settings,
                connector="helix",
                selected_source_ids=payload.sourceIds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ingest_overview_payload(updated)

    @app.post("/api/ingest/jira/test")
    def test_jira_ingest(payload: SourceSelectionRequest) -> dict[str, Any]:
        settings = load_settings()
        sources = _select_sources(
            list(jira_sources(settings)),
            requested_source_ids=payload.sourceIds,
            disabled_source_ids=_json_list_from_settings(
                getattr(settings, "JIRA_INGEST_DISABLED_SOURCES_JSON", "[]")
            ),
        )
        test_source = _pick_test_source(sources)
        if test_source is None:
            raise HTTPException(status_code=400, detail="No hay fuentes Jira seleccionadas.")
        ok, message, _ = execute_jira_ingest(
            settings=settings,
            dry_run=True,
            source=test_source,
        )
        return _single_source_result(connector="jira", ok=ok, message=message)

    @app.post("/api/ingest/helix/test")
    def test_helix_ingest(payload: SourceSelectionRequest) -> dict[str, Any]:
        settings = load_settings()
        sources = _select_sources(
            list(helix_sources(settings)),
            requested_source_ids=payload.sourceIds,
            disabled_source_ids=_json_list_from_settings(
                getattr(settings, "HELIX_INGEST_DISABLED_SOURCES_JSON", "[]")
            ),
        )
        test_source = _pick_test_source(sources)
        if test_source is None:
            raise HTTPException(status_code=400, detail="No hay fuentes Helix seleccionadas.")
        ok, message, _ = execute_helix_ingest(
            browser=str(getattr(settings, "HELIX_BROWSER", "chrome") or "chrome").strip()
            or "chrome",
            country=str(test_source.get("country", "")).strip(),
            source_alias=str(test_source.get("alias", "")).strip(),
            source_id=str(test_source.get("source_id", "")).strip(),
            proxy=str(getattr(settings, "HELIX_PROXY", "") or "").strip(),
            ssl_verify=str(getattr(settings, "HELIX_SSL_VERIFY", "") or "").strip(),
            service_origin_buug=test_source.get("service_origin_buug"),
            service_origin_n1=test_source.get("service_origin_n1"),
            service_origin_n2=test_source.get("service_origin_n2"),
            dry_run=True,
            existing_doc=HelixDocument.empty(),
        )
        return _single_source_result(connector="helix", ok=ok, message=message)

    @app.post("/api/ingest/jira")
    def post_ingest_jira(payload: SourceSelectionRequest) -> dict[str, Any]:
        settings = load_settings()
        sources = _select_sources(
            list(jira_sources(settings)),
            requested_source_ids=payload.sourceIds,
            disabled_source_ids=_json_list_from_settings(
                getattr(settings, "JIRA_INGEST_DISABLED_SOURCES_JSON", "[]")
            ),
        )
        if not sources:
            raise HTTPException(status_code=400, detail="No hay fuentes Jira seleccionadas.")
        return run_jira_ingest(settings, selected_sources=sources)

    @app.post("/api/ingest/helix")
    def post_ingest_helix(payload: SourceSelectionRequest) -> dict[str, Any]:
        settings = load_settings()
        sources = _select_sources(
            list(helix_sources(settings)),
            requested_source_ids=payload.sourceIds,
            disabled_source_ids=_json_list_from_settings(
                getattr(settings, "HELIX_INGEST_DISABLED_SOURCES_JSON", "[]")
            ),
        )
        if not sources:
            raise HTTPException(status_code=400, detail="No hay fuentes Helix seleccionadas.")
        return run_helix_ingest(settings, selected_sources=sources)

    @app.post("/api/reports/executive")
    def executive_report(payload: ReportRequest) -> Response:
        settings = load_settings()
        country = str(payload.country or "").strip()
        source_id = str(payload.sourceId or "").strip()
        if not country or not source_id:
            raise HTTPException(
                status_code=400,
                detail="Selecciona país y fuente para el informe ejecutivo.",
            )
        try:
            artifact = generate_executive_report_artifact(
                settings,
                country=country,
                source_id=source_id,
                filters=build_report_filters(
                    status_filters=payload.status,
                    priority_filters=payload.priority,
                    assignee_filters=payload.assignee,
                    quincenal_scope=payload.quincenalScope,
                ),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filename = download_filename("informe_ejecutivo", ext="pptx")
        return Response(
            content=bytes(getattr(artifact, "content", b"") or b""),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers=_download_headers(filename),
        )

    @app.post("/api/reports/executive/save")
    def executive_report_save(payload: ReportRequest) -> dict[str, Any]:
        settings = load_settings()
        country = str(payload.country or "").strip()
        source_id = str(payload.sourceId or "").strip()
        if not country or not source_id:
            raise HTTPException(
                status_code=400,
                detail="Selecciona país y fuente para el informe ejecutivo.",
            )
        try:
            artifact = generate_executive_report_artifact(
                settings,
                country=country,
                source_id=source_id,
                filters=build_report_filters(
                    status_filters=payload.status,
                    priority_filters=payload.priority,
                    assignee_filters=payload.assignee,
                    quincenal_scope=payload.quincenalScope,
                ),
            )
            export_path = save_report_content(
                settings,
                file_name=str(getattr(artifact, "file_name", "") or "informe_ejecutivo.pptx"),
                content=bytes(getattr(artifact, "content", b"") or b""),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _report_saved_payload(
            saved_path=export_path,
            file_name=str(getattr(artifact, "file_name", "") or export_path.name),
            slide_count=int(getattr(artifact, "slide_count", 0) or 0),
            total_issues=int(getattr(artifact, "total_issues", 0) or 0),
            open_issues=int(getattr(artifact, "open_issues", 0) or 0),
            closed_issues=int(getattr(artifact, "closed_issues", 0) or 0),
        )

    @app.post("/api/reports/period")
    def period_report(payload: ReportRequest) -> Response:
        settings = load_settings()
        country = str(payload.country or "").strip()
        source_ids = [
            str(item).strip() for item in list(payload.sourceIds or []) if str(item).strip()
        ]
        if not country or not source_ids:
            raise HTTPException(
                status_code=400,
                detail="Selecciona país y al menos una fuente para el seguimiento.",
            )
        try:
            artifact = generate_period_followup_report_artifact(
                settings,
                country=country,
                source_ids=source_ids,
                filters=build_report_filters(
                    status_filters=payload.status,
                    priority_filters=payload.priority,
                    assignee_filters=payload.assignee,
                    quincenal_scope=payload.quincenalScope,
                ),
                applied_filter_summary=str(payload.appliedFilterSummary or "").strip(),
                functionality_status_filters=payload.functionalityStatusFilters,
                functionality_priority_filters=payload.functionalityPriorityFilters,
                functionality_filters=payload.functionalityFilters,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filename = download_filename("seguimiento_periodo", ext="pptx")
        return Response(
            content=bytes(getattr(artifact, "content", b"") or b""),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers=_download_headers(filename),
        )

    @app.post("/api/reports/period/save")
    def period_report_save(payload: ReportRequest) -> dict[str, Any]:
        settings = load_settings()
        country = str(payload.country or "").strip()
        source_ids = [
            str(item).strip() for item in list(payload.sourceIds or []) if str(item).strip()
        ]
        if not country or not source_ids:
            raise HTTPException(
                status_code=400,
                detail="Selecciona país y al menos una fuente para el seguimiento.",
            )
        try:
            artifact = generate_period_followup_report_artifact(
                settings,
                country=country,
                source_ids=source_ids,
                filters=build_report_filters(
                    status_filters=payload.status,
                    priority_filters=payload.priority,
                    assignee_filters=payload.assignee,
                    quincenal_scope=payload.quincenalScope,
                ),
                applied_filter_summary=str(payload.appliedFilterSummary or "").strip(),
                functionality_status_filters=payload.functionalityStatusFilters,
                functionality_priority_filters=payload.functionalityPriorityFilters,
                functionality_filters=payload.functionalityFilters,
            )
            export_path = save_report_content(
                settings,
                file_name=str(getattr(artifact, "file_name", "") or "seguimiento_periodo.pptx"),
                content=bytes(getattr(artifact, "content", b"") or b""),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _report_saved_payload(
            saved_path=export_path,
            file_name=str(getattr(artifact, "file_name", "") or export_path.name),
            slide_count=int(getattr(artifact, "slide_count", 0) or 0),
            total_issues=int(getattr(artifact, "total_issues", 0) or 0),
            open_issues=int(getattr(artifact, "open_issues", 0) or 0),
            closed_issues=int(getattr(artifact, "closed_issues", 0) or 0),
        )

    static_dir = _frontend_dist_dir()
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
    else:
        dev_url = _frontend_dev_url()

        @app.get("/", include_in_schema=False)
        def dev_frontend_redirect() -> Response:
            if dev_url:
                return RedirectResponse(dev_url)
            return JSONResponse(
                {
                    "message": (
                        "Frontend no compilado. Ejecuta `make run` o "
                        "`npm --prefix frontend run build`."
                    ),
                },
                status_code=503,
            )

        @app.get("/{full_path:path}", include_in_schema=False)
        def dev_frontend_fallback(full_path: str) -> Response:
            if str(full_path).startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            if dev_url:
                return RedirectResponse(f"{dev_url.rstrip('/')}/{full_path}")
            raise HTTPException(status_code=404, detail="Frontend no disponible")

    return app


app = create_app()
