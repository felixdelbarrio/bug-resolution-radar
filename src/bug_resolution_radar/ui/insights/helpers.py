"""Shared helper functions for insights data preparation and safe rendering."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import pandas as pd

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col, open_issues_only


# -------------------------
# Base helpers
# -------------------------
def safe_df(x: Any) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def col_exists(df: pd.DataFrame, col: str) -> bool:
    return isinstance(df, pd.DataFrame) and (col in df.columns)


def open_only(df: pd.DataFrame) -> pd.DataFrame:
    return open_issues_only(df)


def as_naive_utc(ts: pd.Series) -> pd.Series:
    """Make datetime tz-naive to allow arithmetic with UTC now()."""
    if ts is None or not pd.api.types.is_datetime64_any_dtype(ts):
        return ts
    s = ts.copy()
    try:
        if getattr(s.dt, "tz", None) is not None:
            return s.dt.tz_localize(None)
    except Exception:
        # best-effort for mixed/odd types
        try:
            return s.dt.tz_localize(None)
        except Exception:
            return s
    return s


# -------------------------
# Issue lookup (url + meta)
# -------------------------
def build_issue_lookup(
    dff: pd.DataFrame, *, settings: Settings
) -> Tuple[Dict[str, str], Dict[str, Tuple[str, str, str]]]:
    """
    Returns:
      - key_to_url: key -> url (if present) + __JIRA_BASE__ if available
      - key_to_meta: key -> (status, priority, summary)

    Notes:
      - Normaliza status/priority/summary para evitar NaN y mantener consistencia UI.
      - Si no hay columna 'url', intentará construir url con JIRA_BASE_URL.
    """
    key_to_url: Dict[str, str] = {}
    key_to_meta: Dict[str, Tuple[str, str, str]] = {}
    jira_base = (getattr(settings, "JIRA_BASE_URL", "") or "").strip().rstrip("/")

    if dff is None or dff.empty or not col_exists(dff, "key"):
        if jira_base:
            key_to_url["__JIRA_BASE__"] = jira_base
        return key_to_url, key_to_meta

    cols = ["key"]
    for c in ("url", "status", "priority", "summary"):
        if c in dff.columns:
            cols.append(c)

    df2 = dff.loc[:, cols].copy(deep=False)
    keys = df2["key"].fillna("").astype(str).str.strip()
    valid = keys != ""
    if not bool(valid.any()):
        if jira_base:
            key_to_url["__JIRA_BASE__"] = jira_base
        return key_to_url, key_to_meta

    df2 = df2.loc[valid].copy()
    df2["key"] = keys.loc[valid]
    df2 = df2.drop_duplicates(subset=["key"], keep="first")

    n = len(df2)
    status = (
        normalize_text_col(df2["status"], "(sin estado)").astype(str)
        if "status" in df2.columns
        else pd.Series(["(sin estado)"] * n, index=df2.index, dtype=str)
    )
    priority = (
        normalize_text_col(df2["priority"], "(sin priority)").astype(str)
        if "priority" in df2.columns
        else pd.Series(["(sin priority)"] * n, index=df2.index, dtype=str)
    )
    summary = (
        df2["summary"].fillna("").astype(str)
        if "summary" in df2.columns
        else pd.Series([""] * n, index=df2.index, dtype=str)
    )

    key_vals = df2["key"].to_list()
    key_to_meta = {
        k: (stt, pr, summ)
        for k, stt, pr, summ in zip(
            key_vals, status.to_list(), priority.to_list(), summary.to_list()
        )
    }

    if "url" in df2.columns:
        urls = df2["url"].fillna("").astype(str).str.strip()
        key_to_url.update({k: u for k, u in zip(key_vals, urls.to_list()) if u})

    if jira_base:
        key_to_url["__JIRA_BASE__"] = jira_base
        for k in key_to_meta.keys():
            key_to_url.setdefault(k, f"{jira_base}/browse/{k}")

    return key_to_url, key_to_meta


# -------------------------
# Heuristics (flow + risk)
# -------------------------
def status_bucket(status: str) -> str:
    s = (status or "").strip().lower()

    if "block" in s or "bloque" in s:
        return "bloqueado"

    if s in {"new", "nuevo"}:
        return "entrada"
    if "accept" in s:
        return "entrada"
    if "analys" in s or "analis" in s or "analysis" in s:
        return "entrada"

    if "progress" in s or "progreso" in s:
        return "en_curso"
    if "rework" in s or "wip" in s:
        return "en_curso"

    if "verify" in s or "verif" in s:
        return "salida"
    if "deploy" in s:
        return "salida"
    if s == "test" or "qa" in s:
        return "salida"
    if "done" in s or "closed" in s or "resolved" in s:
        return "salida"

    return "otro"


def priority_weight(p: str) -> float:
    s = (p or "").strip().lower()
    if "highest" in s or s == "p0":
        return 3.0
    if "high" in s or s == "p1":
        return 2.2
    if "medium" in s or s == "p2":
        return 1.4
    if "low" in s or s == "p3":
        return 1.0
    if "lowest" in s:
        return 0.8
    if "imped" in s:
        return 2.6
    if "(sin priority)" in s:
        return 1.0
    return 1.1


def risk_label(score_0_100: float) -> str:
    if score_0_100 >= 70.0:
        return "🔴 Alto"
    if score_0_100 >= 40.0:
        return "🟠 Medio"
    return "🟢 Bajo"


def pct(x: int, total: int) -> float:
    return (float(x) / float(total) * 100.0) if total else 0.0
