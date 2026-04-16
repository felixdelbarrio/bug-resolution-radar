"""CSV/XLSX export helpers for API-driven downloads."""

from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Mapping, Sequence, cast

import pandas as pd

EXCEL_DATETIME_NUMFMT = "dd/mm/yyyy hh:mm:ss"
EXCEL_DEFAULT_HEADER_ROW_HEIGHT = 21.0
EXCEL_DEFAULT_DATA_ROW_HEIGHT = 18.0
EXCEL_ID_COL_MIN_WIDTH = 18.0
EXCEL_ID_COL_MAX_WIDTH = 26.0


def download_filename(prefix: str, *, ext: str) -> str:
    safe = "".join(
        ch
        for ch in str(prefix or "export").strip().replace(" ", "_")
        if ch.isalnum() or ch in {"_", "-", "."}
    )
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    extension = str(ext or "txt").strip().lstrip(".") or "txt"
    return f"{safe or 'export'}_{stamp}.{extension}"


def dataframe_to_csv_bytes(df: pd.DataFrame, *, include_index: bool = False) -> bytes:
    if df is None:
        df = pd.DataFrame()
    csv_text = cast(str, df.to_csv(index=include_index))
    return csv_text.encode("utf-8-sig")


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
    link_specs: list[tuple[str, str]] = []
    if "key" in clean.columns and "url" in clean.columns:
        link_specs = [("key", "url")]
    elif "ID de la Incidencia" in clean.columns and "__item_url__" in clean.columns:
        link_specs = [("ID de la Incidencia", "__item_url__")]
    return dataframes_to_xlsx_bytes(
        [(str(sheet_name or "Export"), clean)],
        include_index=include_index,
        hyperlink_columns_by_sheet={str(sheet_name or "Export"): link_specs}
        if link_specs
        else None,
    )


def _safe_excel_sheet_name(name: str, *, used: set[str]) -> str:
    base = str(name or "Export").strip() or "Export"
    cleaned = "".join(ch for ch in base if ch not in {":", "\\", "/", "?", "*", "[", "]"})
    cleaned = cleaned[:31] or "Export"
    candidate = cleaned
    n = 2
    while candidate in used:
        suffix = f"_{n}"
        candidate = (cleaned[: max(1, 31 - len(suffix))] + suffix)[:31]
        n += 1
    used.add(candidate)
    return candidate


def _prepare_excel_df_for_links(
    df: pd.DataFrame,
    *,
    link_specs: Sequence[tuple[str, str]],
) -> pd.DataFrame:
    out = pd.DataFrame() if df is None else df.copy()
    url_cols_to_drop = [
        url_col
        for visible_col, url_col in link_specs
        if visible_col in out.columns and url_col in out.columns
    ]
    if url_cols_to_drop:
        out = out.drop(columns=url_cols_to_drop, errors="ignore")
    return out


def _excel_safe_df(df: pd.DataFrame) -> pd.DataFrame:
    clean = pd.DataFrame() if df is None else df.copy()
    for column in clean.columns:
        series = clean[column]
        if isinstance(series.dtype, pd.DatetimeTZDtype):
            clean[column] = series.dt.tz_convert("UTC").dt.tz_localize(None)
        elif pd.api.types.is_object_dtype(series.dtype):
            clean[column] = series.map(_safe_excel_scalar)
    return clean


def _excel_text_len(value: Any) -> int:
    return 0 if value is None else len(str(value))


def _find_excel_id_column(df: pd.DataFrame) -> str | None:
    for name in ("ID de la Incidencia", "key", "id"):
        if name in df.columns:
            return name
    return None


def _apply_excel_id_sizing(ws: Any, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    id_col_name = _find_excel_id_column(df)
    if not id_col_name:
        return
    try:
        id_col_idx = int(df.columns.get_loc(id_col_name))
    except Exception:
        return
    max_chars = max(
        _excel_text_len(id_col_name),
        max(_excel_text_len(value) for value in df[id_col_name].tolist()),
    )
    target_width = min(EXCEL_ID_COL_MAX_WIDTH, max(EXCEL_ID_COL_MIN_WIDTH, float(max_chars + 2)))
    ws.set_column(id_col_idx, id_col_idx, float(target_width))
    ws.set_row(0, EXCEL_DEFAULT_HEADER_ROW_HEIGHT)
    for row_idx, id_value in enumerate(df[id_col_name].tolist(), start=1):
        line_count = max(1, str(id_value or "").count("\n") + 1)
        ws.set_row(row_idx, EXCEL_DEFAULT_DATA_ROW_HEIGHT * float(line_count))


def _write_excel_sheet(
    writer: pd.ExcelWriter,
    *,
    sheet_name: str,
    df: pd.DataFrame,
    include_index: bool,
    hyperlink_columns: Sequence[tuple[str, str]] | None,
) -> None:
    src_df = pd.DataFrame() if df is None else df
    link_specs = list(hyperlink_columns or [])
    out_df = _excel_safe_df(_prepare_excel_df_for_links(src_df, link_specs=link_specs))
    out_df.to_excel(writer, index=include_index, sheet_name=sheet_name)
    ws = writer.sheets[sheet_name]
    workbook = writer.book
    _apply_excel_id_sizing(ws, out_df)
    if out_df.empty or not link_specs:
        return
    hyperlink_format = workbook.get_default_url_format()
    col_positions = {str(col): idx + 1 for idx, col in enumerate(out_df.columns.tolist())}
    for visible_col, url_col in link_specs:
        if visible_col not in src_df.columns or url_col not in src_df.columns:
            continue
        target_col = col_positions.get(str(visible_col))
        if target_col is None:
            continue
        for row_idx, (label, url) in enumerate(
            zip(src_df[visible_col].tolist(), src_df[url_col].tolist()),
            start=2,
        ):
            url_txt = str(url or "").strip()
            if not (url_txt.startswith("http://") or url_txt.startswith("https://")):
                continue
            ws.write_url(
                row_idx - 1,
                target_col - 1,
                url_txt,
                hyperlink_format,
                string=str(label or "").strip() or url_txt,
            )


def dataframes_to_xlsx_bytes(
    sheets: Sequence[tuple[str, pd.DataFrame]],
    *,
    include_index: bool = False,
    hyperlink_columns_by_sheet: Mapping[str, Sequence[tuple[str, str]]] | None = None,
) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(
        bio,
        engine="xlsxwriter",
        datetime_format=EXCEL_DATETIME_NUMFMT,
    ) as writer:
        used_sheet_names: set[str] = set()
        if not sheets:
            _write_excel_sheet(
                writer,
                sheet_name=_safe_excel_sheet_name("Export", used=used_sheet_names),
                df=pd.DataFrame(),
                include_index=include_index,
                hyperlink_columns=None,
            )
        for raw_sheet_name, df in sheets:
            safe_sheet_name = _safe_excel_sheet_name(raw_sheet_name, used=used_sheet_names)
            _write_excel_sheet(
                writer,
                sheet_name=safe_sheet_name,
                df=df,
                include_index=include_index,
                hyperlink_columns=list((hyperlink_columns_by_sheet or {}).get(raw_sheet_name, ())),
            )
    return bio.getvalue()
