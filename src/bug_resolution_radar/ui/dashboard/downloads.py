# bug_resolution_radar/ui/dashboard/downloads.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import pandas as pd
import streamlit as st


# -------------------------
# CSV helpers
# -------------------------
@dataclass(frozen=True)
class CsvDownloadSpec:
    filename_prefix: str = "issues_filtradas"
    include_index: bool = False
    encoding: str = "utf-8"
    mime: str = "text/csv"
    date_format: str = "%Y-%m-%d"


def _safe_filename(s: str) -> str:
    s = (s or "").strip().replace(" ", "_")
    keep = []
    for ch in s:
        if ch.isalnum() or ch in {"_", "-", "."}:
            keep.append(ch)
    return "".join(keep) or "export"


def _timestamp() -> str:
    # local-ish timestamp string; good enough for filenames
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def df_to_csv_bytes(df: pd.DataFrame, *, include_index: bool = False, encoding: str = "utf-8") -> bytes:
    """Convert DataFrame to CSV bytes with safe defaults.

    - Dates are serialized by pandas; keep it simple and consistent.
    """
    if df is None:
        df = pd.DataFrame()
    csv = df.to_csv(index=include_index)
    return csv.encode(encoding, errors="replace")


def download_button_for_df(
    df: pd.DataFrame,
    *,
    label: str = "⬇️ Descargar CSV",
    key: str = "download_csv",
    spec: CsvDownloadSpec = CsvDownloadSpec(),
    suffix: str = "",
    disabled: Optional[bool] = None,
    use_container_width: bool = True,
) -> None:
    """Render a download button for a dataframe.

    `disabled` defaults to True if df is empty.
    """
    if df is None:
        df = pd.DataFrame()

    is_empty = df.empty
    if disabled is None:
        disabled = is_empty

    prefix = _safe_filename(spec.filename_prefix)
    suf = _safe_filename(suffix) if suffix else ""
    ts = _timestamp()
    fname = f"{prefix}{'_' + suf if suf else ''}_{ts}.csv"

    csv_bytes = df_to_csv_bytes(df, include_index=spec.include_index, encoding=spec.encoding)

    st.download_button(
        label=label,
        data=csv_bytes,
        file_name=fname,
        mime=spec.mime,
        key=key,
        disabled=disabled,
        use_container_width=use_container_width,
    )


# -------------------------
# "Table view" shaping
# -------------------------
DEFAULT_TABLE_COLS = [
    "key",
    "summary",
    "status",
    "type",
    "priority",
    "assignee",
    "created",
    "updated",
    "resolved",
    "resolution",
    "url",
]


def make_table_export_df(df: pd.DataFrame, *, preferred_cols: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """Return a dataframe shaped like the table view export.

    - Keeps only known/important columns first
    - Preserves extra columns at the end
    - Does not mutate the input df
    """
    if df is None or df.empty:
        return pd.DataFrame()

    dff = df.copy()

    cols_pref = list(preferred_cols) if preferred_cols is not None else DEFAULT_TABLE_COLS
    existing_pref = [c for c in cols_pref if c in dff.columns]
    extra = [c for c in dff.columns if c not in existing_pref]

    out = dff[existing_pref + extra].copy()

    # Keep datetimes readable; pandas will serialize fine, but normalize tz a bit if present
    for c in ["created", "updated", "resolved"]:
        if c in out.columns:
            try:
                out[c] = pd.to_datetime(out[c], errors="coerce")
            except Exception:
                pass

    return out


def render_download_bar(
    df_for_export: pd.DataFrame,
    *,
    key_prefix: str = "issues",
    caption: str = "",
    filename_prefix: str = "issues_filtradas",
    suffix: str = "",
) -> None:
    """Small reusable bar: download button + count/caption."""
    c1, c2 = st.columns([1, 3])
    with c1:
        download_button_for_df(
            df_for_export,
            key=f"{key_prefix}::download_csv",
            spec=CsvDownloadSpec(filename_prefix=filename_prefix),
            suffix=suffix,
            disabled=df_for_export is None or df_for_export.empty,
        )
    with c2:
        if caption:
            st.caption(caption)
        else:
            n = 0 if df_for_export is None else int(len(df_for_export))
            st.caption(f"{n} issues (según filtros actuales)")