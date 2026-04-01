"""Centralized fortnight summary metrics shared by Insights and PPT reports."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

import pandas as pd

from bug_resolution_radar.analytics.status_semantics import (
    effective_closed_mask,
    effective_finalized_at,
)
from bug_resolution_radar.config import Settings, all_configured_sources
from bug_resolution_radar.repositories.helix_repo import HelixRepo

_DEFAULT_QUINCENA_LAST_FINISHED_ONLY = False
_MAESTRA_FLAG_KEYS = (
    "BBVA_SEL_GIM_Maestra",
    "BBVA_MasterIncident",
)
_MAESTRA_TRUE_TOKENS = {"1", "si", "yes", "true", "x", "maestra", "master"}
OPEN_ISSUES_FOCUS_MODE_MAESTRAS = "maestras"
OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH = "criticidad_alta"
DEFAULT_OPEN_ISSUES_FOCUS_MODE = OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH
_CRITICAL_PRIORITY_TOKENS = {
    "suponeunimpedimento",
    "impedimento",
    "highest",
    "high",
}


@dataclass(frozen=True)
class OpenIssueGrouping:
    mode: str
    focus_scope_label: str
    other_scope_label: str
    focus_card_kicker: str
    focus_card_detail: str
    other_card_kicker: str
    other_card_detail: str
    focus_report_label: str
    other_report_label: str


@dataclass(frozen=True)
class QuincenalWindow:
    current_start: pd.Timestamp
    current_end: pd.Timestamp
    previous_start: pd.Timestamp
    previous_end: pd.Timestamp
    month_start: pd.Timestamp


@dataclass(frozen=True)
class QuincenalGroups:
    open_focus: pd.DataFrame
    open_other: pd.DataFrame
    new_now: pd.DataFrame
    new_before: pd.DataFrame
    new_accumulated: pd.DataFrame
    closed_now: pd.DataFrame
    closed_before: pd.DataFrame
    resolved_now: pd.DataFrame
    resolved_before: pd.DataFrame

    @property
    def maestras_open(self) -> pd.DataFrame:
        # Backward-compatible alias: now represents open "focus" group.
        return self.open_focus

    @property
    def others_open(self) -> pd.DataFrame:
        # Backward-compatible alias: now represents open "other" group.
        return self.open_other


@dataclass(frozen=True)
class QuincenalSummary:
    scope_id: str
    scope_label: str
    window: QuincenalWindow
    total_issues: int
    open_total: int
    open_group_mode: str
    open_focus_label: str
    open_other_label: str
    open_focus_card_kicker: str
    open_focus_card_detail: str
    open_other_card_kicker: str
    open_other_card_detail: str
    open_focus_report_label: str
    open_other_report_label: str
    open_focus_total: int
    open_other_total: int
    new_now: int
    new_before: int
    new_accumulated: int
    new_delta_pct: float | None
    closed_now: int
    closed_focus_now: int
    closed_other_now: int
    closed_before: int
    closed_delta_pct: float | None
    resolution_days_now: float | None
    resolved_focus_now: int
    resolved_other_now: int
    resolution_days_before: float | None
    resolution_delta_pct: float | None

    @property
    def maestras_total(self) -> int:
        # Backward-compatible alias: now represents open "focus" total.
        return int(self.open_focus_total)

    @property
    def others_total(self) -> int:
        # Backward-compatible alias: now represents open "other" total.
        return int(self.open_other_total)


@dataclass(frozen=True)
class QuincenalScopeResult:
    summary: QuincenalSummary
    groups: QuincenalGroups
    dff: pd.DataFrame
    open_df: pd.DataFrame


@dataclass(frozen=True)
class QuincenalCountryResult:
    country: str
    source_ids: tuple[str, ...]
    source_label_by_id: Dict[str, str]
    aggregate: QuincenalScopeResult
    by_source: Dict[str, QuincenalScopeResult]


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _to_dt_naive(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return out.dt.tz_convert(None)
    except Exception:
        try:
            return out.dt.tz_localize(None)
        except Exception:
            return out


def _normalize_flag_token(value: object) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    token = unicodedata.normalize("NFKD", token)
    token = "".join(ch for ch in token if not unicodedata.combining(ch))
    return token.strip()


def _compact_token(value: object) -> str:
    token = _normalize_flag_token(value)
    return "".join(ch for ch in token if ch.isalnum())


def normalize_open_issues_focus_mode(value: object) -> str:
    token = _compact_token(value)
    if token in {"maestra", "maestras", "master", "masters"}:
        return OPEN_ISSUES_FOCUS_MODE_MAESTRAS
    if token in {
        "criticidadalta",
        "criticalidadalta",
        "criticalhigh",
        "highcriticality",
        "high",
        "critical",
        "criticidad",
    }:
        return OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH
    return DEFAULT_OPEN_ISSUES_FOCUS_MODE


def open_issues_focus_mode(settings: Settings | None) -> str:
    raw = (
        getattr(settings, "OPEN_ISSUES_FOCUS_MODE", DEFAULT_OPEN_ISSUES_FOCUS_MODE)
        if settings is not None
        else DEFAULT_OPEN_ISSUES_FOCUS_MODE
    )
    return normalize_open_issues_focus_mode(raw)


def open_issue_grouping(settings: Settings | None) -> OpenIssueGrouping:
    mode = open_issues_focus_mode(settings)
    if mode == OPEN_ISSUES_FOCUS_MODE_MAESTRAS:
        return OpenIssueGrouping(
            mode=mode,
            focus_scope_label="Maestras abiertas",
            other_scope_label="Otras incidencias",
            focus_card_kicker="Insights · Maestras",
            focus_card_detail="Abiertas marcadas como maestras",
            other_card_kicker="Insights · Otras",
            other_card_detail="Abiertas no maestras",
            focus_report_label="INCIDENCIAS MAESTRAS",
            other_report_label="OTRAS INCIDENCIAS",
        )
    return OpenIssueGrouping(
        mode=OPEN_ISSUES_FOCUS_MODE_CRITICAL_HIGH,
        focus_scope_label="Incidencias con criticidad alta",
        other_scope_label="Otras incidencias",
        focus_card_kicker="Insights · Criticidad alta",
        focus_card_detail="Abiertas con prioridad Impedimento / High / Highest",
        other_card_kicker="Insights · Otras",
        other_card_detail="Abiertas sin criticidad alta",
        focus_report_label="INCIDENCIAS CON CRITICIDAD ALTA",
        other_report_label="OTRAS INCIDENCIAS",
    )


def _critical_priority_mask(df: pd.DataFrame) -> pd.Series:
    safe = _safe_df(df)
    if safe.empty:
        return pd.Series(False, index=safe.index, dtype=bool)
    if "priority" not in safe.columns:
        return pd.Series(False, index=safe.index, dtype=bool)
    normalized = safe["priority"].fillna("").astype(str).map(_compact_token)
    return normalized.isin(_CRITICAL_PRIORITY_TOKENS).fillna(False).astype(bool)


def _is_truthy_flag(value: object) -> bool:
    token = _normalize_flag_token(value)
    if not token:
        return False
    if token in _MAESTRA_TRUE_TOKENS:
        return True
    # Some Helix tenants persist flags as verbose labels (e.g. "Si (maestra)").
    return any(flag in token for flag in ("si", "yes", "true", "maestra", "master"))


def _extract_raw_flag(raw_fields: Mapping[str, object]) -> object:
    if not isinstance(raw_fields, Mapping):
        return ""
    for key in _MAESTRA_FLAG_KEYS:
        if key in raw_fields:
            return raw_fields.get(key, "")
    folded = {str(k).strip().lower(): v for k, v in raw_fields.items()}
    for key in _MAESTRA_FLAG_KEYS:
        value = folded.get(str(key).strip().lower())
        if value not in (None, ""):
            return value
    return ""


@lru_cache(maxsize=8)
def _load_maestra_merge_keys_cached(helix_path: str, mtime_ns: int) -> frozenset[str]:
    del mtime_ns  # cache invalidation key only
    path = Path(str(helix_path or "").strip())
    if not path.exists():
        return frozenset()

    try:
        doc = HelixRepo(path).load()
    except Exception:
        return frozenset()
    if doc is None or not doc.items:
        return frozenset()

    out: set[str] = set()
    for item in doc.items:
        flag_value = _extract_raw_flag(item.raw_fields or {})
        if not _is_truthy_flag(flag_value):
            continue
        item_id = str(item.id or "").strip().upper()
        source_id = str(item.source_id or "").strip().lower()
        if not item_id:
            continue
        out.add(item_id)
        if source_id:
            out.add(f"{source_id}::{item_id}")
    return frozenset(out)


def maestra_merge_keys(settings: Settings) -> frozenset[str]:
    path = Path(str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip()).expanduser()
    if not path.exists():
        return frozenset()
    try:
        mtime_ns = int(path.stat().st_mtime_ns)
    except Exception:
        mtime_ns = -1
    return _load_maestra_merge_keys_cached(str(path.resolve()), mtime_ns)


def mark_maestra_rows(df: pd.DataFrame, *, settings: Settings) -> pd.Series:
    safe = _safe_df(df)
    if safe.empty or "key" not in safe.columns:
        return pd.Series(False, index=safe.index, dtype=bool)

    maestra_keys = maestra_merge_keys(settings)
    if not maestra_keys:
        return pd.Series(False, index=safe.index, dtype=bool)

    keys = safe["key"].fillna("").astype(str).str.strip().str.upper()
    source_ids = (
        safe["source_id"].fillna("").astype(str).str.strip().str.lower()
        if "source_id" in safe.columns
        else pd.Series("", index=safe.index, dtype=str)
    )
    merge_keys = source_ids + "::" + keys
    merge_keys = merge_keys.where(source_ids.ne(""), keys)
    is_maestra = merge_keys.isin(maestra_keys) | keys.isin(maestra_keys)

    if "source_type" in safe.columns:
        source_type = safe["source_type"].fillna("").astype(str).str.strip().str.lower()
        is_maestra &= source_type.eq("helix")
    return is_maestra.fillna(False).astype(bool)


def _parse_bool_flag(value: object, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if not token:
        return bool(default)
    if token in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "f", "no", "n", "off"}:
        return False
    return bool(default)


def _quincena_last_finished_only(settings: Settings) -> bool:
    return _parse_bool_flag(
        getattr(settings, "QUINCENA_LAST_FINISHED_ONLY", _DEFAULT_QUINCENA_LAST_FINISHED_ONLY),
        default=_DEFAULT_QUINCENA_LAST_FINISHED_ONLY,
    )


def _infer_reference_day_from_df(df: pd.DataFrame | None) -> pd.Timestamp | None:
    safe = _safe_df(df)
    if safe.empty:
        return None

    candidates: list[pd.Timestamp] = []
    for column in ("updated", "resolved", "created"):
        if column not in safe.columns:
            continue
        parsed = _to_dt_naive(safe[column]).dropna()
        if parsed.empty:
            continue
        candidates.append(pd.Timestamp(parsed.max()))

    if not candidates:
        finalized = _to_dt_naive(effective_finalized_at(safe)).dropna()
        if not finalized.empty:
            candidates.append(pd.Timestamp(finalized.max()))

    if not candidates:
        return None
    return max(candidates).normalize()


def _analysis_reference_day(
    *,
    reference_day: pd.Timestamp | None = None,
    df: pd.DataFrame | None = None,
) -> pd.Timestamp:
    if reference_day is not None:
        ts = pd.Timestamp(reference_day)
        try:
            ts = ts.tz_convert(None)
        except Exception:
            try:
                ts = ts.tz_localize(None)
            except Exception:
                pass
        return ts.normalize()

    inferred = _infer_reference_day_from_df(df)
    if inferred is not None:
        return inferred
    return pd.Timestamp.now().normalize()


def _window_from_reference(
    reference_day: pd.Timestamp,
    *,
    last_finished_only: bool,
) -> QuincenalWindow:
    anchor = pd.Timestamp(reference_day).normalize()
    month_start = anchor.replace(day=1)
    month_end = (month_start + pd.offsets.MonthBegin(1) - pd.Timedelta(days=1)).normalize()

    if last_finished_only:
        if int(anchor.day) <= 15:
            previous_month_end = month_start - pd.Timedelta(days=1)
            current_start = previous_month_end.replace(day=16)
            current_end = previous_month_end
        else:
            current_start = month_start
            current_end = month_start + pd.Timedelta(days=14)
    else:
        if int(anchor.day) <= 15:
            current_start = month_start
            current_end = month_start + pd.Timedelta(days=14)
        else:
            current_start = month_start + pd.Timedelta(days=15)
            current_end = month_end

    if int(current_start.day) == 1:
        previous_end = current_start - pd.Timedelta(days=1)
        previous_start = previous_end.replace(day=16)
    else:
        previous_start = current_start.replace(day=1)
        previous_end = current_start - pd.Timedelta(days=1)
    accumulated_month_start = current_start.replace(day=1)

    return QuincenalWindow(
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=previous_end,
        month_start=accumulated_month_start,
    )


def _delta_pct(now_value: float | int, before_value: float | int) -> float | None:
    now_val = float(now_value or 0.0)
    before_val = float(before_value or 0.0)
    if before_val <= 0:
        if now_val <= 0:
            return 0.0
        return None
    return (now_val - before_val) / before_val


def _focus_group_mask(
    df: pd.DataFrame,
    *,
    grouping: OpenIssueGrouping,
    settings: Settings,
) -> pd.Series:
    safe = _safe_df(df)
    if safe.empty:
        return pd.Series(False, index=safe.index, dtype=bool)
    if grouping.mode == OPEN_ISSUES_FOCUS_MODE_MAESTRAS:
        return mark_maestra_rows(safe, settings=settings)
    return _critical_priority_mask(safe)


def _focus_other_counts(
    df: pd.DataFrame,
    *,
    grouping: OpenIssueGrouping,
    settings: Settings,
) -> tuple[int, int]:
    safe = _safe_df(df)
    if safe.empty:
        return 0, 0
    focus_mask = _focus_group_mask(safe, grouping=grouping, settings=settings)
    focus_total = int(focus_mask.sum())
    other_total = max(int(len(safe)) - focus_total, 0)
    return focus_total, other_total


def _issue_listing(
    df: pd.DataFrame,
    *,
    source_label_by_id: Mapping[str, str],
    resolution_col: str | None = None,
) -> pd.DataFrame:
    safe = _safe_df(df)
    if safe.empty:
        cols = [
            "key",
            "summary",
            "status",
            "priority",
            "assignee",
            "source",
            "created",
            "resolved",
        ]
        if resolution_col:
            cols.append("resolution_days")
        return pd.DataFrame(columns=cols)

    out = pd.DataFrame(index=safe.index)
    out["key"] = safe["key"].fillna("").astype(str) if "key" in safe.columns else ""
    out["summary"] = (
        safe["summary"].fillna("").astype(str).str.strip() if "summary" in safe.columns else ""
    )
    out["status"] = safe["status"].fillna("").astype(str) if "status" in safe.columns else ""
    out["priority"] = safe["priority"].fillna("").astype(str) if "priority" in safe.columns else ""
    out["assignee"] = (
        safe["assignee"].fillna("").astype(str).replace("", "(sin asignar)")
        if "assignee" in safe.columns
        else "(sin asignar)"
    )
    source_ids = (
        safe["source_id"].fillna("").astype(str).str.strip()
        if "source_id" in safe.columns
        else pd.Series("", index=safe.index, dtype=str)
    )
    out["source"] = source_ids.map(lambda sid: source_label_by_id.get(str(sid), str(sid)))

    created = (
        _to_dt_naive(safe["created"])
        if "created" in safe.columns
        else pd.Series(pd.NaT, index=safe.index, dtype="datetime64[ns]")
    )
    resolved = (
        _to_dt_naive(safe["resolved"])
        if "resolved" in safe.columns
        else pd.Series(pd.NaT, index=safe.index, dtype="datetime64[ns]")
    )
    out["created"] = created.dt.strftime("%Y-%m-%d")
    out["resolved"] = resolved.dt.strftime("%Y-%m-%d")
    out["created"] = out["created"].fillna("")
    out["resolved"] = out["resolved"].fillna("")

    if resolution_col and resolution_col in safe.columns:
        out["resolution_days"] = pd.to_numeric(safe[resolution_col], errors="coerce").round(1)

    sort_cols: List[str] = []
    ascending: List[bool] = []
    if "created" in out.columns:
        sort_cols.append("created")
        ascending.append(False)
    sort_cols.append("key")
    ascending.append(True)
    out = out.sort_values(by=sort_cols, ascending=ascending, na_position="last", kind="mergesort")
    return out.reset_index(drop=True)


def _scope_df(df: pd.DataFrame, *, country: str, source_ids: Sequence[str]) -> pd.DataFrame:
    safe = _safe_df(df)
    if safe.empty:
        return safe

    mask = pd.Series(True, index=safe.index)
    country_txt = str(country or "").strip()
    if country_txt and "country" in safe.columns:
        mask &= safe["country"].fillna("").astype(str).eq(country_txt)

    source_tokens = [str(sid or "").strip() for sid in list(source_ids or []) if str(sid).strip()]
    if source_tokens and "source_id" in safe.columns:
        mask &= safe["source_id"].fillna("").astype(str).isin(source_tokens)

    return safe.loc[mask].copy(deep=False)


def _scope_result(
    *,
    df: pd.DataFrame,
    settings: Settings,
    scope_id: str,
    scope_label: str,
    source_label_by_id: Mapping[str, str],
    reference_day: pd.Timestamp,
) -> QuincenalScopeResult:
    safe = _safe_df(df)
    window = _window_from_reference(
        reference_day,
        last_finished_only=_quincena_last_finished_only(settings),
    )
    grouping = open_issue_grouping(settings)

    closed_mask = effective_closed_mask(safe)
    open_df = safe.loc[~closed_mask].copy(deep=False) if not safe.empty else pd.DataFrame()
    open_focus_mask = _focus_group_mask(open_df, grouping=grouping, settings=settings)
    open_focus = open_df.loc[open_focus_mask].copy(deep=False)
    open_other = open_df.loc[~open_focus_mask].copy(deep=False)

    created = _to_dt_naive(safe["created"]) if "created" in safe.columns else pd.Series(pd.NaT)
    created_day = created.dt.normalize()
    new_now_mask = created_day.between(window.current_start, window.current_end, inclusive="both")
    new_before_mask = created_day.between(
        window.previous_start, window.previous_end, inclusive="both"
    )
    new_accumulated_mask = created_day.between(
        window.month_start, window.current_end, inclusive="both"
    )

    finalized = _to_dt_naive(effective_finalized_at(safe))
    finalized_day = finalized.dt.normalize()
    closed_now_mask = finalized_day.between(
        window.current_start, window.current_end, inclusive="both"
    )
    closed_before_mask = finalized_day.between(
        window.previous_start, window.previous_end, inclusive="both"
    )

    closed_now = safe.loc[closed_now_mask].copy(deep=False)
    closed_before = safe.loc[closed_before_mask].copy(deep=False)
    closed_focus_now, closed_other_now = _focus_other_counts(
        closed_now,
        grouping=grouping,
        settings=settings,
    )

    resolution_source = safe.copy(deep=False)
    resolution_source["__created"] = created
    resolution_source["__finalized"] = finalized
    resolution_source = resolution_source[
        resolution_source["__created"].notna() & resolution_source["__finalized"].notna()
    ].copy(deep=False)
    if resolution_source.empty:
        resolved_now = pd.DataFrame()
        resolved_before = pd.DataFrame()
    else:
        resolution_source["resolution_days"] = (
            (resolution_source["__finalized"] - resolution_source["__created"]).dt.total_seconds()
            / 86400.0
        ).clip(lower=0.0)
        finalized_norm = resolution_source["__finalized"].dt.normalize()
        resolved_now = resolution_source.loc[
            finalized_norm.between(window.current_start, window.current_end, inclusive="both")
        ].copy(deep=False)
        resolved_before = resolution_source.loc[
            finalized_norm.between(window.previous_start, window.previous_end, inclusive="both")
        ].copy(deep=False)

    resolution_now_days = (
        float(pd.to_numeric(resolved_now["resolution_days"], errors="coerce").mean())
        if not resolved_now.empty
        else None
    )
    resolved_focus_now, resolved_other_now = _focus_other_counts(
        resolved_now,
        grouping=grouping,
        settings=settings,
    )
    resolution_before_days = (
        float(pd.to_numeric(resolved_before["resolution_days"], errors="coerce").mean())
        if not resolved_before.empty
        else None
    )
    resolution_delta_pct = (
        _delta_pct(resolution_now_days, resolution_before_days)
        if resolution_now_days is not None and resolution_before_days is not None
        else None
    )

    groups = QuincenalGroups(
        open_focus=_issue_listing(open_focus, source_label_by_id=source_label_by_id),
        open_other=_issue_listing(open_other, source_label_by_id=source_label_by_id),
        new_now=_issue_listing(
            safe.loc[new_now_mask].copy(deep=False),
            source_label_by_id=source_label_by_id,
        ),
        new_before=_issue_listing(
            safe.loc[new_before_mask].copy(deep=False),
            source_label_by_id=source_label_by_id,
        ),
        new_accumulated=_issue_listing(
            safe.loc[new_accumulated_mask].copy(deep=False),
            source_label_by_id=source_label_by_id,
        ),
        closed_now=_issue_listing(closed_now, source_label_by_id=source_label_by_id),
        closed_before=_issue_listing(closed_before, source_label_by_id=source_label_by_id),
        resolved_now=_issue_listing(
            resolved_now,
            source_label_by_id=source_label_by_id,
            resolution_col="resolution_days",
        ),
        resolved_before=_issue_listing(
            resolved_before,
            source_label_by_id=source_label_by_id,
            resolution_col="resolution_days",
        ),
    )

    summary = QuincenalSummary(
        scope_id=str(scope_id or "").strip(),
        scope_label=str(scope_label or "").strip() or str(scope_id or "").strip(),
        window=window,
        total_issues=int(len(safe)),
        open_total=int(len(open_df)),
        open_group_mode=str(grouping.mode),
        open_focus_label=str(grouping.focus_scope_label),
        open_other_label=str(grouping.other_scope_label),
        open_focus_card_kicker=str(grouping.focus_card_kicker),
        open_focus_card_detail=str(grouping.focus_card_detail),
        open_other_card_kicker=str(grouping.other_card_kicker),
        open_other_card_detail=str(grouping.other_card_detail),
        open_focus_report_label=str(grouping.focus_report_label),
        open_other_report_label=str(grouping.other_report_label),
        open_focus_total=int(len(open_focus)),
        open_other_total=int(len(open_other)),
        new_now=int(new_now_mask.sum()),
        new_before=int(new_before_mask.sum()),
        new_accumulated=int(new_accumulated_mask.sum()),
        new_delta_pct=_delta_pct(int(new_now_mask.sum()), int(new_before_mask.sum())),
        closed_now=int(closed_now_mask.sum()),
        closed_focus_now=int(closed_focus_now),
        closed_other_now=int(closed_other_now),
        closed_before=int(closed_before_mask.sum()),
        closed_delta_pct=_delta_pct(int(closed_now_mask.sum()), int(closed_before_mask.sum())),
        resolution_days_now=resolution_now_days,
        resolved_focus_now=int(resolved_focus_now),
        resolved_other_now=int(resolved_other_now),
        resolution_days_before=resolution_before_days,
        resolution_delta_pct=resolution_delta_pct,
    )
    return QuincenalScopeResult(summary=summary, groups=groups, dff=safe, open_df=open_df)


def source_label_map(
    settings: Settings,
    *,
    country: str | None = None,
    source_ids: Sequence[str] | None = None,
) -> Dict[str, str]:
    selected_source_ids = {
        str(sid or "").strip() for sid in list(source_ids or []) if str(sid or "").strip()
    }
    out: Dict[str, str] = {}
    for src in all_configured_sources(settings, country=country):
        sid = str(src.get("source_id") or "").strip()
        if not sid:
            continue
        if selected_source_ids and sid not in selected_source_ids:
            continue
        alias = str(src.get("alias") or "").strip() or sid
        source_type = str(src.get("source_type") or "").strip().upper() or "SOURCE"
        out[sid] = f"{alias} · {source_type}"
    for sid in selected_source_ids:
        out.setdefault(sid, sid)
    return out


def scope_country_sources(
    df: pd.DataFrame,
    *,
    country: str,
    source_ids: Sequence[str],
) -> pd.DataFrame:
    return _scope_df(df, country=country, source_ids=source_ids)


def build_country_quincenal_result(
    *,
    df: pd.DataFrame,
    settings: Settings,
    country: str,
    source_ids: Sequence[str],
    source_label_by_id: Mapping[str, str] | None = None,
    reference_day: pd.Timestamp | None = None,
) -> QuincenalCountryResult:
    country_txt = str(country or "").strip()
    selected_source_ids = tuple(
        str(sid or "").strip() for sid in list(source_ids or []) if str(sid or "").strip()
    )
    labels = dict(source_label_by_id or source_label_map(settings, country=country_txt))
    scoped = _scope_df(df, country=country_txt, source_ids=selected_source_ids)
    normalized_reference_day = _analysis_reference_day(
        reference_day=reference_day,
        df=scoped,
    )

    aggregate = _scope_result(
        df=scoped,
        settings=settings,
        scope_id=country_txt,
        scope_label=country_txt or "País",
        source_label_by_id=labels,
        reference_day=normalized_reference_day,
    )

    by_source: Dict[str, QuincenalScopeResult] = {}
    for sid in selected_source_ids:
        source_df = (
            scoped.loc[scoped["source_id"].fillna("").astype(str).eq(sid)].copy(deep=False)
            if "source_id" in scoped.columns
            else pd.DataFrame()
        )
        by_source[sid] = _scope_result(
            df=source_df,
            settings=settings,
            scope_id=sid,
            scope_label=labels.get(sid, sid),
            source_label_by_id=labels,
            reference_day=normalized_reference_day,
        )

    return QuincenalCountryResult(
        country=country_txt,
        source_ids=selected_source_ids,
        source_label_by_id=labels,
        aggregate=aggregate,
        by_source=by_source,
    )


def format_window_label(window: QuincenalWindow) -> str:
    start = window.current_start.strftime("%d/%m")
    end = window.current_end.strftime("%d/%m/%Y")
    return f"Periodo {start} - {end}"


def ordered_country_sources(
    source_ids: Iterable[str], *, source_label_by_id: Mapping[str, str]
) -> List[str]:
    unique: List[str] = []
    seen: set[str] = set()
    for sid in source_ids:
        token = str(sid or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return sorted(unique, key=lambda sid: source_label_by_id.get(sid, sid).lower())
