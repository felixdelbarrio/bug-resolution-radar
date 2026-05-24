"""JIRA/Helix finalist-state cross checks.

This module is the single source of truth for:
- extracting Helix incident ids from JIRA functional text,
- linking JIRA rows with Helix rows inside the active country/scope,
- evaluating final-state discrepancies,
- applying the effective finalist state recovered by the ad hoc Helix lookup.

The effective finalist timestamp uses Helix ``resolved`` when available. If
Helix is already in a finalist status but lacks ``resolved``, ``updated`` is used
as a proxy for the final-state transition. The proxy is only applied while the
timestamp falls inside the applicable reference window so a Helix closure outside
the viewed period does not close a JIRA issue inside that period.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Sequence
from uuid import uuid4

import pandas as pd

from bug_resolution_radar.analytics.issues import priority_rank, status_progress_rank
from bug_resolution_radar.analytics.status_semantics import is_finalist_status
from bug_resolution_radar.common.issue_links import (
    HELIX_ID_RE,
    build_helix_issue_url,
    build_jira_issue_url,
)
from bug_resolution_radar.config import Settings, jira_sources

POST_JQL_LOOKUP_HELIX_SOURCE_ALIAS = "Lookup estados finalistas Jira"
POST_JQL_LOOKUP_HELIX_KIND = "post_jql_inc_lookup"

LOGGER = logging.getLogger(__name__)

_DISCREPANCY_COLUMNS: tuple[str, ...] = (
    "country",
    "helix_id",
    "helix_key",
    "helix_summary",
    "helix_description",
    "helix_status",
    "helix_status_is_finalist",
    "helix_resolved",
    "helix_updated",
    "helix_url",
    "jira_key",
    "jira_summary",
    "jira_description",
    "jira_status",
    "jira_status_is_finalist",
    "jira_created",
    "jira_updated",
    "jira_resolved",
    "jira_open_days",
    "jira_priority",
    "jira_assignee",
    "po_team_leader",
    "jira_url",
    "source_id",
    "source_alias",
    "helix_source_id",
    "helix_source_alias",
    "helix_finalized_at",
)


def is_post_jql_lookup_helix_source(
    source_id: str | None,
    source_alias: str | None,
    helix_lookup_kind: str | None = None,
) -> bool:
    """Return whether a Helix row comes from the ad hoc post-JQL INC lookup."""
    kind = str(helix_lookup_kind or "").strip().lower()
    if kind == POST_JQL_LOOKUP_HELIX_KIND:
        return True
    alias = str(source_alias or "").strip().casefold()
    if alias == POST_JQL_LOOKUP_HELIX_SOURCE_ALIAS.casefold():
        return True
    sid = str(source_id or "").strip().casefold()
    return sid.startswith("helix:") and sid.endswith(":lookup-estados-finalistas-jira")


def extract_helix_ids_from_text(text: object) -> tuple[str, ...]:
    """Return normalized unique Helix ids found in free text."""
    if text is None:
        return ()
    raw = str(text)
    if not raw:
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for match in HELIX_ID_RE.finditer(raw):
        token = str(match.group(0) or "").strip().upper()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return tuple(out)


def _empty_discrepancies() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_DISCREPANCY_COLUMNS))


def _safe_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _series_text(df: pd.DataFrame, column: str, *, default: str = "") -> pd.Series:
    if column not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype=object)
    return df[column].fillna(default).astype(str)


def _to_dt_naive(series: pd.Series | None, *, index: pd.Index | None = None) -> pd.Series:
    if series is None:
        return pd.Series(pd.NaT, index=index, dtype="datetime64[ns]")
    out = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return out.dt.tz_convert(None)
    except Exception:
        try:
            return out.dt.tz_localize(None)
        except Exception:
            return out


def _country_mask(df: pd.DataFrame, country: str | None) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    country_txt = str(country or "").strip()
    if country_txt and "country" in df.columns:
        mask &= _series_text(df, "country").str.strip().eq(country_txt)
    return mask


def _source_type(df: pd.DataFrame) -> pd.Series:
    if "source_type" not in df.columns:
        if "source_id" in df.columns:
            return _series_text(df, "source_id").str.split(":", n=1).str[0].str.lower()
        return pd.Series(["jira"] * len(df), index=df.index, dtype=object)
    return _series_text(df, "source_type").str.strip().str.lower()


def _source_mask(df: pd.DataFrame, source_ids: Sequence[str] | None) -> pd.Series:
    tokens = [str(item or "").strip() for item in list(source_ids or [])]
    tokens = [item for item in tokens if item]
    if not tokens or "source_id" not in df.columns:
        return pd.Series(True, index=df.index)
    return _series_text(df, "source_id").str.strip().isin(tokens)


def _helix_id_from_key(values: pd.Series) -> pd.Series:
    return (
        values.fillna("")
        .astype(str)
        .str.extract(r"\b(INC\d{8,})\b", flags=re.IGNORECASE)[0]
        .fillna("")
        .str.upper()
    )


def _scope_for_links(
    df: pd.DataFrame,
    *,
    country: str | None,
    source_ids: Sequence[str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    country_filtered = df.loc[_country_mask(df, country)].copy(deep=False)
    if country_filtered.empty:
        return pd.DataFrame(), pd.DataFrame()

    stype = _source_type(country_filtered)
    selected_mask = _source_mask(country_filtered, source_ids)
    jira_mask = stype.eq("jira")
    helix_mask = stype.eq("helix")
    jira_df = country_filtered.loc[jira_mask & selected_mask].copy(deep=False)
    if jira_df.empty and not list(source_ids or []):
        jira_df = country_filtered.loc[jira_mask].copy(deep=False)
    helix_source_id = _series_text(country_filtered, "source_id")
    helix_source_alias = _series_text(country_filtered, "source_alias")
    helix_lookup_kind = _series_text(country_filtered, "helix_lookup_kind")
    ad_hoc_mask = pd.Series(
        [
            is_post_jql_lookup_helix_source(sid, alias, kind)
            for sid, alias, kind in zip(
                helix_source_id.tolist(),
                helix_source_alias.tolist(),
                helix_lookup_kind.tolist(),
            )
        ],
        index=country_filtered.index,
    )
    helix_df = country_filtered.loc[helix_mask & ad_hoc_mask].copy(deep=False)
    return jira_df, helix_df


def build_jira_helix_links(
    df: pd.DataFrame,
    *,
    country: str | None = None,
    source_ids: Sequence[str] | None = None,
    run_id: str = "",
) -> pd.DataFrame:
    """Build vectorized JIRA-to-Helix links based on Helix ids in JIRA text fields."""
    log_run_id = str(run_id or uuid4().hex[:12])
    safe = _safe_frame(df)
    if safe.empty:
        return _empty_discrepancies()

    jira_df, helix_df = _scope_for_links(
        safe,
        country=country,
        source_ids=source_ids,
    )
    if jira_df.empty or helix_df.empty:
        return _empty_discrepancies()

    jira = jira_df.copy(deep=False)
    # Real JQL feeds may carry the Helix incident in either the long description
    # or the short title/summary. We scan both once, dedupe extracted IDs, and
    # keep the actual row relationship 1:N through explode + merge.
    jira_text = _series_text(jira, "description") + "\n" + _series_text(jira, "summary")
    jira["__helix_ids"] = jira_text.map(extract_helix_ids_from_text)
    jira = jira.loc[jira["__helix_ids"].map(bool)].copy(deep=False)
    if jira.empty:
        return _empty_discrepancies()
    jira = jira.explode("__helix_ids", ignore_index=False).copy(deep=False)
    jira["helix_id"] = jira["__helix_ids"].fillna("").astype(str).str.upper()
    jira = jira.loc[jira["helix_id"].ne("")].copy(deep=False)
    if jira.empty:
        return _empty_discrepancies()

    helix = helix_df.copy(deep=False)
    helix["helix_id"] = _helix_id_from_key(_series_text(helix, "key"))
    if "id" in helix.columns:
        missing = helix["helix_id"].eq("")
        if missing.any():
            helix.loc[missing, "helix_id"] = _helix_id_from_key(_series_text(helix, "id")).loc[
                missing
            ]
    helix = helix.loc[helix["helix_id"].ne("")].copy(deep=False)
    if helix.empty:
        return _empty_discrepancies()

    jira_side = pd.DataFrame(
        {
            "country": _series_text(jira, "country"),
            "helix_id": jira["helix_id"],
            "jira_key": _series_text(jira, "key"),
            "jira_summary": _series_text(jira, "summary"),
            "jira_description": _series_text(jira, "description"),
            "jira_status": _series_text(jira, "status"),
            "jira_created": jira["created"] if "created" in jira.columns else pd.NaT,
            "jira_updated": jira["updated"] if "updated" in jira.columns else pd.NaT,
            "jira_resolved": jira["resolved"] if "resolved" in jira.columns else pd.NaT,
            "jira_priority": _series_text(jira, "priority"),
            "jira_assignee": _series_text(jira, "assignee"),
            "po_team_leader": _series_text(jira, "po_team_leader"),
            "jira_url": _series_text(jira, "url"),
            "source_id": _series_text(jira, "source_id"),
            "source_alias": _series_text(jira, "source_alias"),
        },
        index=jira.index,
    )
    helix_side = pd.DataFrame(
        {
            "helix_id": helix["helix_id"],
            "helix_key": _series_text(helix, "key"),
            "helix_summary": _series_text(helix, "summary"),
            "helix_description": _series_text(helix, "description"),
            "helix_status": _series_text(helix, "status"),
            "helix_resolved": helix["resolved"] if "resolved" in helix.columns else pd.NaT,
            "helix_updated": helix["updated"] if "updated" in helix.columns else pd.NaT,
            "helix_url": _series_text(helix, "url"),
            "helix_source_id": _series_text(helix, "source_id"),
            "helix_source_alias": _series_text(helix, "source_alias"),
        },
        index=helix.index,
    )
    helix_before = int(len(helix_side))
    helix_side = helix_side.drop_duplicates(subset=["helix_id"], keep="first")
    helix_duplicates_removed = max(helix_before - int(len(helix_side)), 0)
    links = jira_side.merge(helix_side, on="helix_id", how="inner", sort=False)
    if links.empty:
        return _empty_discrepancies()
    links_before = int(len(links))
    links = links.drop_duplicates(
        subset=["country", "source_id", "jira_key", "helix_id"],
        keep="first",
    )
    duplicates_removed = max(links_before - int(len(links)), 0) + helix_duplicates_removed
    for helix_id, bucket in links.groupby("helix_id", sort=False):
        jira_keys = sorted(
            {
                str(value or "").strip().upper()
                for value in bucket["jira_key"].tolist()
                if str(value or "").strip()
            }
        )
        LOGGER.info(
            "finalist_jira_helix_links",
            extra={
                "run_id": log_run_id,
                "helix_id": str(helix_id or ""),
                "jira_keys": jira_keys,
                "jira_count": len(jira_keys),
                "matched_by": "jira_text_helix_id",
                "duplicates_removed": int(duplicates_removed),
                "excluded_reason": "",
            },
        )
    for column in _DISCREPANCY_COLUMNS:
        if column not in links.columns:
            links[column] = pd.NA
    return links.loc[:, list(_DISCREPANCY_COLUMNS)].copy(deep=False)


def _finalized_at(
    df: pd.DataFrame,
    *,
    resolved_col: str,
    updated_col: str,
    finalist_mask: pd.Series,
) -> pd.Series:
    resolved = _to_dt_naive(
        df[resolved_col] if resolved_col in df.columns else None, index=df.index
    )
    updated = _to_dt_naive(df[updated_col] if updated_col in df.columns else None, index=df.index)
    finalized = resolved.copy()
    missing = finalized.isna() & finalist_mask.fillna(False).astype(bool)
    if missing.any():
        finalized.loc[missing] = updated.loc[missing]
    return finalized.where(finalist_mask.fillna(False).astype(bool))


def _reference_end(reference_day: pd.Timestamp | str | None) -> pd.Timestamp | None:
    if reference_day is None:
        return None
    ts = pd.Timestamp(reference_day)
    if ts.tzinfo is not None:
        try:
            ts = ts.tz_convert(None)
        except Exception:
            ts = ts.tz_localize(None)
    return ts


def build_finalist_status_discrepancies(
    df: pd.DataFrame,
    *,
    settings: Settings,
    country: str,
    source_ids: Sequence[str],
    reference_day: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Return JIRA-open/Helix-finalist discrepancies for the requested scope."""
    run_id = uuid4().hex[:12]
    links = build_jira_helix_links(
        df,
        country=country,
        source_ids=source_ids,
        run_id=run_id,
    )
    if links.empty:
        LOGGER.info(
            "finalist_discrepancies_empty",
            extra={
                "run_id": run_id,
                "helix_id": "",
                "jira_keys": [],
                "jira_count": 0,
                "matched_by": "jira_text_helix_id",
                "duplicates_removed": 0,
                "excluded_reason": "no_jira_helix_links",
            },
        )
        return _empty_discrepancies()

    work = links.copy(deep=False)
    source_po_by_id = {
        str(source.get("source_id") or "").strip(): str(source.get("po_team_leader") or "").strip()
        for source in jira_sources(settings)
        if str(source.get("source_id") or "").strip()
        and str(source.get("po_team_leader") or "").strip()
    }
    if source_po_by_id:
        existing_po = _series_text(work, "po_team_leader")
        source_id_values = _series_text(work, "source_id")
        work["po_team_leader"] = [
            current.strip() or source_po_by_id.get(source_id.strip(), "")
            for current, source_id in zip(existing_po.tolist(), source_id_values.tolist())
        ]
    work["helix_status_is_finalist"] = work["helix_status"].map(is_finalist_status).astype(bool)
    work["jira_status_is_finalist"] = work["jira_status"].map(is_finalist_status).astype(bool)
    work["helix_finalized_at"] = _finalized_at(
        work,
        resolved_col="helix_resolved",
        updated_col="helix_updated",
        finalist_mask=work["helix_status_is_finalist"],
    )
    jira_resolved = _to_dt_naive(work["jira_resolved"], index=work.index)
    jira_created = _to_dt_naive(work["jira_created"], index=work.index)
    jira_updated = _to_dt_naive(work["jira_updated"], index=work.index)
    work["jira_created"] = jira_created
    work["jira_updated"] = jira_updated
    work["jira_resolved"] = jira_resolved
    work["helix_resolved"] = _to_dt_naive(work["helix_resolved"], index=work.index)
    work["helix_updated"] = _to_dt_naive(work["helix_updated"], index=work.index)

    ref_end = _reference_end(reference_day)
    if ref_end is not None:
        work = work.loc[work["helix_finalized_at"].notna() & work["helix_finalized_at"].le(ref_end)]

    if work.empty:
        LOGGER.info(
            "finalist_discrepancies_empty",
            extra={
                "run_id": run_id,
                "helix_id": "",
                "jira_keys": [],
                "jira_count": 0,
                "matched_by": "jira_text_helix_id",
                "duplicates_removed": 0,
                "excluded_reason": "helix_finalized_outside_window",
            },
        )
        return _empty_discrepancies()

    jira_base_url = str(getattr(settings, "JIRA_BASE_URL", "") or "").strip()
    helix_base_url = str(
        getattr(settings, "HELIX_ARSQL_DASHBOARD_URL", "")
        or getattr(settings, "HELIX_DASHBOARD_URL", "")
        or ""
    ).strip()
    work["jira_url"] = [
        build_jira_issue_url(key, base_url=jira_base_url, existing_url=url)
        for key, url in zip(work["jira_key"].tolist(), work["jira_url"].tolist())
    ]
    work["helix_url"] = [
        build_helix_issue_url(helix_id, base_url=helix_base_url, existing_url=url)
        for helix_id, url in zip(work["helix_id"].tolist(), work["helix_url"].tolist())
    ]

    reference = ref_end or pd.Timestamp.now().normalize()
    work["jira_open_days"] = (
        ((reference - work["jira_created"]).dt.total_seconds() / 86400.0)
        .clip(lower=0.0)
        .fillna(0.0)
    )
    mask = (
        work["helix_status_is_finalist"].fillna(False).astype(bool)
        & ~work["jira_status_is_finalist"].fillna(False).astype(bool)
        & work["jira_resolved"].isna()
        & work["helix_finalized_at"].notna()
    )
    out = work.loc[mask].copy(deep=False)
    if out.empty:
        LOGGER.info(
            "finalist_discrepancies_empty",
            extra={
                "run_id": run_id,
                "helix_id": "",
                "jira_keys": [],
                "jira_count": 0,
                "matched_by": "jira_text_helix_id",
                "duplicates_removed": 0,
                "excluded_reason": "no_open_jira_with_finalist_helix",
            },
        )
        return _empty_discrepancies()
    out["__priority_rank"] = out["jira_priority"].map(priority_rank).fillna(99)
    out["__status_rank"] = out["jira_status"].map(status_progress_rank).fillna(99)
    out = out.sort_values(
        by=["__priority_rank", "jira_open_days", "__status_rank", "helix_id", "jira_key"],
        ascending=[True, False, True, True, True],
        kind="mergesort",
    )
    for helix_id, bucket in out.groupby("helix_id", sort=False):
        jira_keys = [
            str(value or "").strip().upper()
            for value in bucket["jira_key"].tolist()
            if str(value or "").strip()
        ]
        LOGGER.info(
            "finalist_discrepancies_built",
            extra={
                "run_id": run_id,
                "helix_id": str(helix_id or ""),
                "jira_keys": jira_keys,
                "jira_count": len(jira_keys),
                "matched_by": "jira_text_helix_id",
                "duplicates_removed": 0,
                "excluded_reason": "",
            },
        )
    return out.loc[:, list(_DISCREPANCY_COLUMNS)].copy(deep=False)


def _window_end(reference_window: Any) -> pd.Timestamp | None:
    if reference_window is None:
        return None
    if isinstance(reference_window, dict):
        for key in ("end", "current_end", "to", "reference_day"):
            if key in reference_window:
                return _reference_end(reference_window.get(key))
        return None
    if isinstance(reference_window, (tuple, list)):
        if len(reference_window) >= 2:
            return _reference_end(reference_window[1])
        if len(reference_window) == 1:
            return _reference_end(reference_window[0])
        return None
    for attr in ("end", "current_end", "to", "reference_day"):
        if hasattr(reference_window, attr):
            return _reference_end(getattr(reference_window, attr))
    return _reference_end(reference_window)


def apply_effective_finalist_lookup_state(
    df: pd.DataFrame,
    *,
    discrepancies: pd.DataFrame,
    reference_window: Any = None,
) -> pd.DataFrame:
    """Mark linked JIRA rows as effectively resolved from ad hoc Helix finalist data."""
    safe = _safe_frame(df)
    if safe.empty or not isinstance(discrepancies, pd.DataFrame) or discrepancies.empty:
        return safe.copy(deep=False)
    if "key" not in safe.columns:
        return safe.copy(deep=False)

    needed = {"jira_key", "source_id", "helix_finalized_at", "helix_id", "helix_status"}
    if not needed.issubset(set(discrepancies.columns)):
        return safe.copy(deep=False)

    disc = discrepancies.copy(deep=False)
    disc["helix_finalized_at"] = _to_dt_naive(disc["helix_finalized_at"], index=disc.index)
    end = _window_end(reference_window)
    if end is not None:
        disc = disc.loc[disc["helix_finalized_at"].notna() & disc["helix_finalized_at"].le(end)]
    else:
        disc = disc.loc[disc["helix_finalized_at"].notna()]
    if disc.empty:
        return safe.copy(deep=False)

    disc = disc.sort_values(
        by=["helix_finalized_at", "helix_id"],
        ascending=[True, True],
        kind="mergesort",
    ).drop_duplicates(subset=["source_id", "jira_key"], keep="first")

    helper = disc.loc[
        :,
        ["source_id", "jira_key", "helix_finalized_at", "helix_id", "helix_status"],
    ].rename(
        columns={
            "source_id": "__source_id",
            "jira_key": "__jira_key",
            "helix_finalized_at": "__helix_finalized_at",
            "helix_id": "__effective_helix_id",
            "helix_status": "__effective_helix_status",
        }
    )
    work = safe.copy(deep=False)
    stale_helper_cols = [
        column
        for column in (
            "__helix_finalized_at",
            "__effective_helix_id",
            "__effective_helix_status",
            "__effective_finalist_by_helix",
        )
        if column in work.columns
    ]
    if stale_helper_cols:
        work = work.drop(columns=stale_helper_cols)
    work["__jira_key"] = _series_text(work, "key").str.strip()
    work["__source_id"] = _series_text(work, "source_id").str.strip()
    work = work.merge(helper, on=["__source_id", "__jira_key"], how="left", sort=False)
    has_effective = work["__helix_finalized_at"].notna()
    if not has_effective.any():
        return safe.copy(deep=False)

    if "resolved" not in work.columns:
        work["resolved"] = pd.NaT
    resolved = _to_dt_naive(work["resolved"], index=work.index)
    work["resolved"] = resolved.where(resolved.notna(), work["__helix_finalized_at"])
    work["__effective_finalist_by_helix"] = has_effective
    cleanup = [col for col in ("__source_id", "__jira_key") if col in work.columns]
    return work.drop(columns=cleanup).copy(deep=False)


def apply_effective_finalist_lookup_state_for_scope(
    scoped_df: pd.DataFrame,
    *,
    history_df: pd.DataFrame,
    settings: Settings,
    country: str,
    source_ids: Sequence[str],
    reference_day: pd.Timestamp | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply historical Helix finalist state to the active, already-filtered scope."""
    safe_scope = _safe_frame(scoped_df)
    history = _safe_frame(history_df)
    lookup_df = history if not history.empty else safe_scope
    discrepancies = build_finalist_status_discrepancies(
        lookup_df,
        settings=settings,
        country=country,
        source_ids=source_ids,
        reference_day=reference_day,
    )
    if discrepancies.empty:
        return safe_scope.copy(deep=False), discrepancies
    return (
        apply_effective_finalist_lookup_state(
            safe_scope,
            discrepancies=discrepancies,
            reference_window=reference_day,
        ),
        discrepancies,
    )
