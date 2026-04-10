"""Backend reporting service with explicit filter inputs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

from bug_resolution_radar.analytics.analysis_window import apply_analysis_depth_filter
from bug_resolution_radar.analytics.issues import normalize_text_col
from bug_resolution_radar.analytics.quincenal_scope import (
    QUINCENAL_SCOPE_ALL,
    apply_issue_key_scope,
    normalize_quincenal_scope_label,
    quincenal_scope_options,
)
from bug_resolution_radar.analytics.status_semantics import effective_closed_mask
from bug_resolution_radar.config import Settings
from bug_resolution_radar.repositories.issues_store import load_issues_df
from bug_resolution_radar.reports.executive_ppt import (
    ExecutiveReportResult,
    generate_scope_executive_ppt,
)
from bug_resolution_radar.reports.period_followup_ppt import (
    PeriodFollowupReportResult,
    generate_country_period_followup_ppt,
)


@dataclass(frozen=True)
class ReportFilters:
    status: tuple[str, ...] = ()
    priority: tuple[str, ...] = ()
    assignee: tuple[str, ...] = ()
    quincenal_scope: str = QUINCENAL_SCOPE_ALL


@dataclass(frozen=True)
class PreparedReportContext:
    scoped_df: pd.DataFrame
    dff: pd.DataFrame
    open_df: pd.DataFrame


def _configured_export_path(settings: Settings) -> Path | None:
    configured = str(getattr(settings, "REPORT_PPT_DOWNLOAD_DIR", "") or "").strip()
    if not configured:
        return None
    return Path(configured).expanduser()


def default_report_export_dir(settings: Settings) -> Path:
    """Resolve preferred export directory without touching disk unless needed."""
    configured = _configured_export_path(settings)
    candidates: list[Path] = []
    if configured is not None:
        candidates.append(Path(configured).expanduser())
    candidates.append((Path.home() / "Downloads").expanduser())

    for candidate in candidates:
        txt = str(candidate).strip()
        if not txt:
            continue
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if candidate.is_dir():
                return candidate
        except Exception:
            continue
    return Path.cwd()


def ensure_report_export_dir(settings: Settings) -> Path:
    """Create export dir only during an explicit save action."""
    export_dir = default_report_export_dir(settings)
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if export_dir.is_dir():
        return export_dir
    return Path.cwd()


def unique_report_export_path(export_dir: Path, *, file_name: str) -> Path:
    name = str(file_name or "").strip() or "radar-export.pptx"
    target = export_dir / name
    if not target.exists():
        return target
    stem = target.stem or "radar-export"
    suffix = target.suffix or ".pptx"
    for idx in range(1, 1000):
        candidate = export_dir / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    return export_dir / f"{stem}_{os.getpid()}{suffix}"


def save_report_content(
    settings: Settings,
    *,
    file_name: str,
    content: bytes,
) -> Path:
    """Persist generated report bytes to the configured export directory."""
    export_dir = ensure_report_export_dir(settings)
    export_path = unique_report_export_path(export_dir, file_name=file_name)
    export_path.write_bytes(bytes(content or b""))
    return export_path


def _normalize_tokens(values: Sequence[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return tuple(out)


def build_report_filters(
    *,
    status_filters: Sequence[str] | None = None,
    priority_filters: Sequence[str] | None = None,
    assignee_filters: Sequence[str] | None = None,
    quincenal_scope: object = QUINCENAL_SCOPE_ALL,
) -> ReportFilters:
    return ReportFilters(
        status=_normalize_tokens(status_filters),
        priority=_normalize_tokens(priority_filters),
        assignee=_normalize_tokens(assignee_filters),
        quincenal_scope=normalize_quincenal_scope_label(quincenal_scope),
    )


def _scope_source_df(df: pd.DataFrame, *, country: str, source_id: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)
    country_txt = str(country or "").strip()
    source_txt = str(source_id or "").strip()
    if country_txt and "country" in df.columns:
        mask &= df["country"].fillna("").astype(str).eq(country_txt)
    if source_txt and "source_id" in df.columns:
        mask &= df["source_id"].fillna("").astype(str).eq(source_txt)
    return df.loc[mask].copy(deep=False)


def _scope_country_sources(
    df: pd.DataFrame,
    *,
    country: str,
    source_ids: Sequence[str],
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    country_txt = str(country or "").strip()
    source_tokens = [str(source_id or "").strip() for source_id in list(source_ids or [])]
    source_tokens = [token for token in source_tokens if token]
    mask = pd.Series(True, index=df.index)
    if country_txt and "country" in df.columns:
        mask &= df["country"].fillna("").astype(str).eq(country_txt)
    if source_tokens and "source_id" in df.columns:
        mask &= df["source_id"].fillna("").astype(str).isin(source_tokens)
    return df.loc[mask].copy(deep=False)


def _apply_explicit_filters(df: pd.DataFrame, filters: ReportFilters) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)
    status_norm: pd.Series | None = None
    if "status" in df.columns:
        status_norm = normalize_text_col(df["status"], "(sin estado)")
        if filters.status:
            mask &= status_norm.isin(list(filters.status))

    priority_norm: pd.Series | None = None
    if "priority" in df.columns:
        priority_norm = normalize_text_col(df["priority"], "(sin priority)")
        if filters.priority:
            mask &= priority_norm.isin(list(filters.priority))

    if filters.assignee and "assignee" in df.columns:
        assignee_norm = normalize_text_col(df["assignee"], "(sin asignar)")
        mask &= assignee_norm.isin(list(filters.assignee))

    dff = df.loc[mask].copy(deep=False)
    if status_norm is not None:
        dff["status"] = status_norm.loc[mask].to_numpy()
    if priority_norm is not None:
        dff["priority"] = priority_norm.loc[mask].to_numpy()
    return dff


def _apply_quincenal_scope(
    df: pd.DataFrame,
    *,
    settings: Settings,
    country: str,
    source_ids: Sequence[str],
    selected_scope: str,
) -> pd.DataFrame:
    scope_label = normalize_quincenal_scope_label(selected_scope)
    if scope_label == QUINCENAL_SCOPE_ALL or df is None or df.empty:
        return df.copy(deep=False)

    options = quincenal_scope_options(
        df,
        settings=settings,
        country=str(country or "").strip(),
        source_ids=source_ids,
    )
    selected_keys = options.get(scope_label)
    if selected_keys is None:
        return df.copy(deep=False)
    return apply_issue_key_scope(df, keys=selected_keys)


def _build_context_for_scope(
    settings: Settings,
    *,
    country: str,
    source_ids: Sequence[str],
    filters: ReportFilters,
    df_all: pd.DataFrame | None = None,
) -> PreparedReportContext:
    base_df = df_all if isinstance(df_all, pd.DataFrame) else load_issues_df(settings.DATA_PATH)
    clean_source_ids = [str(source_id or "").strip() for source_id in list(source_ids or [])]
    clean_source_ids = [token for token in clean_source_ids if token]

    if len(clean_source_ids) == 1:
        scoped_df = _scope_source_df(base_df, country=country, source_id=clean_source_ids[0])
    else:
        scoped_df = _scope_country_sources(base_df, country=country, source_ids=clean_source_ids)

    scoped_df = apply_analysis_depth_filter(scoped_df, settings=settings)
    dff = _apply_explicit_filters(scoped_df, filters)
    dff = _apply_quincenal_scope(
        dff,
        settings=settings,
        country=country,
        source_ids=clean_source_ids,
        selected_scope=filters.quincenal_scope,
    )
    closed_mask = effective_closed_mask(dff) if not dff.empty else pd.Series(dtype=bool)
    open_df = dff.loc[~closed_mask].copy(deep=False) if not dff.empty else pd.DataFrame()
    return PreparedReportContext(scoped_df=scoped_df, dff=dff, open_df=open_df)


def generate_executive_report_artifact(
    settings: Settings,
    *,
    country: str,
    source_id: str,
    filters: ReportFilters,
    df_all: pd.DataFrame | None = None,
) -> ExecutiveReportResult:
    context = _build_context_for_scope(
        settings,
        country=country,
        source_ids=[source_id],
        filters=filters,
        df_all=df_all,
    )
    if context.scoped_df.empty:
        raise ValueError("No hay datos en el scope seleccionado.")
    if context.dff.empty:
        raise ValueError("No hay incidencias tras aplicar la ventana temporal y los filtros.")

    return generate_scope_executive_ppt(
        settings,
        country=country,
        source_id=source_id,
        status_filters=list(filters.status),
        priority_filters=list(filters.priority),
        assignee_filters=list(filters.assignee),
        dff_override=context.dff,
        open_df_override=context.open_df,
        scoped_source_df_override=context.scoped_df,
    )


def generate_period_followup_report_artifact(
    settings: Settings,
    *,
    country: str,
    source_ids: Sequence[str],
    filters: ReportFilters,
    applied_filter_summary: str = "",
    functionality_status_filters: Sequence[str] | None = None,
    functionality_priority_filters: Sequence[str] | None = None,
    functionality_filters: Sequence[str] | None = None,
    df_all: pd.DataFrame | None = None,
) -> PeriodFollowupReportResult:
    context = _build_context_for_scope(
        settings,
        country=country,
        source_ids=source_ids,
        filters=filters,
        df_all=df_all,
    )
    if context.dff.empty:
        raise ValueError("No hay incidencias en la ventana temporal y filtros seleccionados.")

    return generate_country_period_followup_ppt(
        settings,
        country=country,
        source_ids=source_ids,
        dff_override=context.dff,
        open_df_override=context.open_df,
        applied_filter_summary=applied_filter_summary,
        functionality_status_filters=functionality_status_filters,
        functionality_priority_filters=functionality_priority_filters,
        functionality_filters=functionality_filters,
    )
