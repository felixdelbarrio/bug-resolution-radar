"""CSV/XLSX export helpers for API-driven downloads."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import pandas as pd


def download_filename(prefix: str, *, ext: str) -> str:
    safe = "".join(ch for ch in str(prefix or "export").strip().replace(" ", "_") if ch.isalnum() or ch in {"_", "-", "."})
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    extension = str(ext or "txt").strip().lstrip(".") or "txt"
    return f"{safe or 'export'}_{stamp}.{extension}"


def dataframe_to_csv_bytes(df: pd.DataFrame, *, include_index: bool = False) -> bytes:
    if df is None:
        df = pd.DataFrame()
    return df.to_csv(index=include_index).encode("utf-8-sig")


def _safe_excel_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        if value.tzinfo is not None:
            return value.tz_convert("UTC").tz_localize(None).to_pydatetime()
        return value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    return value


def dataframe_to_xlsx_bytes(
    df: pd.DataFrame,
    *,
    sheet_name: str = "Export",
    include_index: bool = False,
) -> bytes:
    clean = pd.DataFrame() if df is None else df.copy()
    for column in clean.columns:
        series = clean[column]
        if isinstance(series.dtype, pd.DatetimeTZDtype):
            clean[column] = series.dt.tz_convert("UTC").dt.tz_localize(None)
        elif pd.api.types.is_object_dtype(series.dtype):
            clean[column] = series.map(_safe_excel_scalar)

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        clean.to_excel(writer, index=include_index, sheet_name=str(sheet_name or "Export")[:31])
    return bio.getvalue()
