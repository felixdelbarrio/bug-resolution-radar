"""Issues tab orchestration and view mode selection."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema_helix import HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.ui.cache import streamlit_cache_df_hash
from bug_resolution_radar.ui.common import priority_rank
from bug_resolution_radar.ui.components.issues import (
    prepare_issue_cards_df,
    render_issue_cards,
    render_issue_table,
)
from bug_resolution_radar.ui.dashboard.constants import canonical_status_rank_map
from bug_resolution_radar.ui.dashboard.exports.downloads import (
    CsvDownloadSpec,
    build_download_filename,
    df_to_excel_bytes,
    dfs_to_excel_bytes,
    download_button_for_df,
    make_table_export_df,
)
from bug_resolution_radar.ui.dashboard.exports.helix_official_export import (
    build_helix_official_export_frames,
)

MAX_CARDS_RENDER = 120
CARDS_PAGE_SIZE = 30
_ISSUES_PERF_BUDGETS_MS: dict[str, dict[str, float]] = {
    "Cards": {
        "filters": 95.0,
        "exports": 45.0,
        "cards": 210.0,
        "total": 380.0,
    },
    "Tabla": {
        "filters": 95.0,
        "exports": 45.0,
        "table": 235.0,
        "total": 420.0,
    },
}
ISSUES_TABLE_PREFERRED_COLS: list[str] = [
    "key",
    "summary",
    "description",
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
_SORT_LABELS: dict[str, str] = {
    "updated": "Updated",
    "created": "Created",
    "resolved": "Resolved",
    "status": "Status",
    "priority": "Priority",
    "assignee": "Assignee",
    "type": "Type",
    "summary": "Summary",
    "description": "Description",
    "key": "ID",
    "country": "Country",
    "source_type": "Origen",
}


def _issues_perf_budget(view: str) -> dict[str, float]:
    return _ISSUES_PERF_BUDGETS_MS.get(str(view or ""), _ISSUES_PERF_BUDGETS_MS["Cards"])


def _elapsed_ms(start_ts: float) -> float:
    return max(0.0, (perf_counter() - float(start_ts)) * 1000.0)


def _issues_perf_budget_overruns(
    *,
    view: str,
    metrics_ms: dict[str, float],
) -> list[str]:
    budgets = _issues_perf_budget(view)
    ordered = ["filters", "cards" if view == "Cards" else "table", "exports", "total"]
    out: list[str] = []
    for block in ordered:
        budget = float(budgets.get(block, 0.0) or 0.0)
        value = float(metrics_ms.get(block, 0.0) or 0.0)
        if budget > 0.0 and value > budget:
            out.append(block)
    return out


def _render_issues_perf_footer(
    *,
    key_prefix: str,
    view: str,
    metrics_ms: dict[str, float],
) -> None:
    budgets = _issues_perf_budget(view)
    ordered = ["filters", "cards" if view == "Cards" else "table", "exports", "total"]
    parts: list[str] = []
    for block in ordered:
        if block not in metrics_ms:
            continue
        value = float(metrics_ms.get(block, 0.0) or 0.0)
        budget = float(budgets.get(block, 0.0) or 0.0)
        if budget > 0:
            parts.append(f"{block} {value:.0f}/{budget:.0f}ms")
        else:
            parts.append(f"{block} {value:.0f}ms")

    overruns = _issues_perf_budget_overruns(view=view, metrics_ms=metrics_ms)
    st.session_state[f"{key_prefix}::perf_snapshot"] = {
        "view": view,
        "metrics_ms": {k: float(v) for k, v in metrics_ms.items()},
        "budget_ms": {k: float(v) for k, v in budgets.items()},
        "overruns": list(overruns),
    }
    if parts:
        st.caption(f"Perf {view}: {' · '.join(parts)}")
    if overruns:
        st.caption(f"Budget excedido en: {', '.join(overruns)}")


def _sorted_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if "updated" in df.columns:
        return df.sort_values(by="updated", ascending=False)
    return df.copy()


def _set_issues_view(view_key: str, value: str) -> None:
    st.session_state[view_key] = value


def _default_issue_sort_col(df: pd.DataFrame) -> str:
    options = _sort_columns_for_controls(df)
    if options:
        return str(options[0])
    if "key" in df.columns:
        return "key"
    return str(df.columns[0]) if not df.empty else "updated"


def _default_sort_asc(sort_col: str) -> bool:
    return str(sort_col or "").strip().lower() not in {"updated", "created", "resolved"}


def _ensure_shared_sort_state(df: pd.DataFrame, *, key_prefix: str) -> tuple[str, bool]:
    sort_col_key = f"{key_prefix}::sort_col"
    sort_asc_key = f"{key_prefix}::sort_asc"
    options = _sort_columns_for_controls(df)
    default_col = _default_issue_sort_col(df)

    sort_col = str(st.session_state.get(sort_col_key) or "").strip()
    if not sort_col or (options and sort_col not in options):
        sort_col = default_col

    if sort_asc_key not in st.session_state:
        st.session_state[sort_asc_key] = _default_sort_asc(sort_col)

    sort_asc = bool(st.session_state.get(sort_asc_key, _default_sort_asc(sort_col)))
    return sort_col, sort_asc


def _sort_columns_for_controls(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty:
        return []
    preferred = [c for c in ISSUES_TABLE_PREFERRED_COLS if c != "url"] + ["country", "source_type"]
    out: list[str] = [c for c in preferred if c in df.columns]
    extra = [c for c in df.columns if c not in out and c != "url"]
    extra_sorted = sorted(extra, key=lambda x: str(x).casefold())
    return out + extra_sorted


def _sort_label(col: str) -> str:
    return _SORT_LABELS.get(str(col), str(col))


def _render_shared_sort_controls(df: pd.DataFrame, *, key_prefix: str) -> None:
    sort_col_key = f"{key_prefix}::sort_col"
    sort_col, _ = _ensure_shared_sort_state(df, key_prefix=key_prefix)
    options = _sort_columns_for_controls(df)
    if not options:
        return
    if sort_col_key in st.session_state:
        current = str(st.session_state.get(sort_col_key) or "").strip()
        if current and current not in options:
            # Let selectbox fall back to first option instead of forcing an invalid value.
            del st.session_state[sort_col_key]

    c_sort, c_search = st.columns([1.35, 1.45], gap="small")
    with c_sort:
        st.selectbox(
            "Ordenar por",
            options=options,
            key=sort_col_key,
            width="stretch",
            format_func=lambda x: _sort_label(str(x)),
        )
    selected_col = str(st.session_state.get(sort_col_key) or sort_col or options[0]).strip()
    search_key = f"{key_prefix}::sort_like_query"
    with c_search:
        st.text_input(
            f"Buscar similares por {_sort_label(selected_col)}",
            key=search_key,
            width="stretch",
            placeholder=f"Like sobre {_sort_label(selected_col)}",
            help="Búsqueda parcial (like) sobre el campo seleccionado en 'Ordenar por'.",
        )


def _render_sort_direction_control(*, key_prefix: str) -> None:
    sort_asc_key = f"{key_prefix}::sort_asc"
    st.toggle("Ascendente", key=sort_asc_key, width="stretch")


def _cards_pagination_window(*, total_rows: int, page_size: int, page: int) -> tuple[int, int, int, int]:
    total = max(0, int(total_rows))
    size = max(1, int(page_size))
    total_pages = max(1, int(math.ceil(total / size)) if total else 1)
    current_page = min(max(1, int(page)), total_pages)
    start = (current_page - 1) * size
    end = min(total, start + size)
    return current_page, start, end, total_pages


def _set_cards_page(page_key: str, value: int) -> None:
    st.session_state[page_key] = max(1, int(value))


def _render_pager_shell(
    *,
    shell_key: str,
    page_key: str,
    page: int,
    total_pages: int,
    start_idx: int,
    end_idx: int,
    total_rows: int,
    prev_button_key: str,
    next_button_key: str,
) -> None:
    with st.container(border=True, key=shell_key):
        nav_prev, nav_info, nav_next = st.columns([0.85, 1.3, 0.85], gap="small")
        nav_prev.button(
            "◀ Anterior",
            key=prev_button_key,
            width="stretch",
            disabled=(page <= 1),
            on_click=_set_cards_page,
            args=(page_key, page - 1),
        )
        nav_info.markdown(
            (
                "<div style='text-align:center; opacity:0.92; "
                "line-height:1.25; padding-top:0.18rem;'>"
                f"<strong>Página {page} de {total_pages}</strong><br/>"
                f"Mostrando {start_idx + 1:,}-{end_idx:,} de {total_rows:,}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        nav_next.button(
            "Siguiente ▶",
            key=next_button_key,
            width="stretch",
            disabled=(page >= total_pages),
            on_click=_set_cards_page,
            args=(page_key, page + 1),
        )


@st.cache_data(
    show_spinner=False,
    max_entries=48,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _cached_apply_shared_like_filter(
    df: pd.DataFrame, *, sort_col: str, query: str
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if sort_col not in df.columns:
        return df
    if not query:
        return df

    col = df[sort_col]
    try:
        if pd.api.types.is_datetime64_any_dtype(col) or isinstance(col.dtype, pd.DatetimeTZDtype):
            text = pd.to_datetime(col, errors="coerce", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
        elif pd.api.types.is_numeric_dtype(col):
            text = col.astype("string")
        else:
            text = col.astype("string")
        mask = text.fillna("").str.contains(query, case=False, regex=False, na=False)
    except Exception:
        text = col.astype(str)
        mask = text.str.contains(query, case=False, regex=False, na=False)

    if bool(mask.all()):
        return df
    return df.loc[mask]


def _apply_shared_like_filter(df: pd.DataFrame, *, sort_col: str, key_prefix: str) -> pd.DataFrame:
    """Apply a lightweight literal-like filter over the selected sort column."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if sort_col not in df.columns:
        return df

    query_key = f"{key_prefix}::sort_like_query"
    query = str(st.session_state.get(query_key) or "").strip()
    if not query:
        return df

    return _cached_apply_shared_like_filter(df, sort_col=sort_col, query=query)


@st.cache_data(
    show_spinner=False,
    max_entries=48,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _apply_shared_sort(df: pd.DataFrame, *, sort_col: str, sort_asc: bool) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if sort_col not in df.columns:
        return df

    out = df.copy()
    sort_col_norm = str(sort_col).strip().lower()
    key_col = "__sort_shared_key"
    tie_col = "__sort_shared_updated"

    if sort_col_norm == "status":
        rank_map = canonical_status_rank_map()
        status_vals = out[sort_col].fillna("").astype(str).str.strip().str.lower()
        out[key_col] = status_vals.map(rank_map).fillna(10_000).astype(int)
    elif sort_col_norm == "priority":
        out[key_col] = (
            out[sort_col].fillna("").astype(str).map(priority_rank).fillna(99).astype(int)
        )
    elif sort_col_norm in {"created", "updated", "resolved"}:
        out[key_col] = pd.to_datetime(out[sort_col], errors="coerce", utc=True)
    else:
        out[key_col] = out[sort_col].fillna("").astype(str).str.casefold()

    sort_cols = [key_col]
    asc = [bool(sort_asc)]
    if sort_col_norm != "updated" and "updated" in out.columns:
        out[tie_col] = pd.to_datetime(out["updated"], errors="coerce", utc=True)
        sort_cols.append(tie_col)
        asc.append(False)

    out = out.sort_values(by=sort_cols, ascending=asc, kind="mergesort", na_position="last")
    return out.drop(columns=[key_col, tie_col], errors="ignore")


@st.cache_data(
    show_spinner=False,
    max_entries=48,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _cached_prepare_cards_df(
    dff: pd.DataFrame, *, max_cards: int, preserve_order: bool
) -> pd.DataFrame:
    return prepare_issue_cards_df(dff, max_cards=max_cards, preserve_order=preserve_order)


@lru_cache(maxsize=8)
def _load_helix_items_by_merge_key_cached(
    helix_path: str, mtime_ns: int
) -> dict[str, HelixWorkItem]:
    del mtime_ns  # cache invalidation key only
    try:
        doc = HelixRepo(Path(helix_path)).load()
    except Exception:
        return {}
    if doc is None:
        return {}

    out: dict[str, HelixWorkItem] = {}
    for item in doc.items:
        sid = str(item.source_id or "").strip().lower()
        item_id = str(item.id or "").strip().upper()
        if not item_id:
            continue
        key = f"{sid}::{item_id}" if sid else item_id
        out[key] = item
    return out


def _helix_data_path_and_mtime(settings: Settings | None) -> tuple[str, int]:
    if settings is None:
        return "", -1
    helix_path = (
        str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip() or "data/helix_dump.json"
    )
    p = Path(helix_path)
    if not p.exists():
        return "", -1
    try:
        return str(p.resolve()), int(p.stat().st_mtime_ns)
    except Exception:
        return str(p), -1


def _extract_helix_item_description(item: HelixWorkItem) -> str:
    raw = item.raw_fields if isinstance(item.raw_fields, dict) else {}
    if not raw:
        return ""

    summary = str(item.summary or "").strip()
    candidate_keys = (
        "Detailed Decription",
        "Detailed Description",
        "Descripción Detallada",
        "Descripcion Detallada",
        "Description",
        "summary",
    )
    for key in candidate_keys:
        value = raw.get(key)
        text = str(value or "").strip()
        if not text or text == ".":
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if summary and text.lower() == summary.lower():
            continue
        return text
    return ""


@lru_cache(maxsize=8)
def _load_helix_descriptions_cached(helix_path: str, mtime_ns: int) -> dict[str, str]:
    items = _load_helix_items_by_merge_key_cached(helix_path, mtime_ns)
    if not items:
        return {}

    out: dict[str, str] = {}
    for merge_key, item in items.items():
        desc = _extract_helix_item_description(item)
        if not desc:
            continue
        out[merge_key] = desc
        item_id = str(item.id or "").strip().upper()
        if item_id and item_id not in out:
            out[item_id] = desc
    return out


def _inject_helix_descriptions(
    dff: pd.DataFrame,
    *,
    settings: Settings | None,
) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame() if dff is None else dff
    if "source_type" not in dff.columns or "key" not in dff.columns:
        return dff

    helix_path, helix_mtime_ns = _helix_data_path_and_mtime(settings)
    if not helix_path:
        return dff
    desc_map = _load_helix_descriptions_cached(helix_path, helix_mtime_ns)
    if not desc_map:
        return dff
    return _inject_helix_descriptions_from_desc_map(dff, desc_map=desc_map)


def _inject_helix_descriptions_from_desc_map(
    dff: pd.DataFrame,
    *,
    desc_map: dict[str, str],
) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame() if dff is None else dff
    if not desc_map:
        return dff
    if "source_type" not in dff.columns or "key" not in dff.columns:
        return dff

    stype = dff["source_type"].astype(str).str.strip().str.lower()
    helix_mask = stype.eq("helix")
    if not bool(helix_mask.any()):
        return dff

    out = dff.copy()
    if "description" not in out.columns:
        out["description"] = ""
    key_upper = out["key"].fillna("").astype(str).str.strip().str.upper()
    if "source_id" in out.columns:
        source_id = out["source_id"].fillna("").astype(str).str.strip().str.lower()
        merge_key = source_id + "::" + key_upper
        merge_key = merge_key.where(source_id.ne(""), key_upper)
    else:
        merge_key = key_upper

    desc_from_merge = merge_key.map(desc_map)
    desc_from_key = key_upper.map(desc_map)
    resolved_desc = desc_from_merge.fillna(desc_from_key).fillna("").astype(str).str.strip()
    has_desc = resolved_desc.ne("")

    current_desc = out["description"].fillna("").astype(str).str.strip()
    summary_txt = out["summary"].fillna("").astype(str).str.strip() if "summary" in out.columns else ""
    keep_current = (
        current_desc.ne("")
        & current_desc.ne("—")
        & current_desc.str.casefold().ne(summary_txt.str.casefold() if isinstance(summary_txt, pd.Series) else "")
    )
    replace_mask = helix_mask & has_desc & ~keep_current
    if bool(replace_mask.any()):
        out.loc[replace_mask, "description"] = resolved_desc.loc[replace_mask]
    return out


def _inject_missing_jira_descriptions_from_summary(dff: pd.DataFrame) -> pd.DataFrame:
    """Do not synthesize Jira descriptions from summary text.

    Earlier fallback logic split summary by separators and copied the tail into
    `description`, which caused duplicated/incorrect descriptions. We now keep
    description empty when Jira did not provide it.
    """
    if dff is None or dff.empty:
        return pd.DataFrame() if dff is None else dff
    if "source_type" not in dff.columns:
        return dff
    if "description" in dff.columns:
        return dff
    out = dff.copy(deep=False).copy()
    out["description"] = ""
    return out


@st.cache_data(
    show_spinner=False,
    max_entries=48,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _cached_prepare_issues_base_df(
    dff: pd.DataFrame,
    *,
    helix_path: str,
    helix_mtime_ns: int,
) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame() if dff is None else dff
    out = _sorted_for_display(dff)
    desc_map = (
        _load_helix_descriptions_cached(helix_path, helix_mtime_ns) if helix_path else {}
    )
    out = _inject_helix_descriptions_from_desc_map(out, desc_map=desc_map)
    return _inject_missing_jira_descriptions_from_summary(out)


@st.cache_data(
    show_spinner=False,
    max_entries=48,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _cached_make_table_export_df(dff: pd.DataFrame) -> pd.DataFrame:
    return make_table_export_df(dff, preferred_cols=ISSUES_TABLE_PREFERRED_COLS)


@st.cache_data(
    show_spinner=False,
    max_entries=24,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _cached_standard_issues_export_xlsx(export_df: pd.DataFrame) -> bytes | None:
    if export_df is None or export_df.empty:
        return None
    return df_to_excel_bytes(export_df, include_index=False, sheet_name="Issues")


@st.cache_data(
    show_spinner=False,
    max_entries=24,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _cached_helix_issues_export_xlsx(
    export_df: pd.DataFrame,
    *,
    helix_path: str,
    helix_mtime_ns: int,
) -> bytes | None:
    if export_df is None or export_df.empty:
        return None
    if not helix_path:
        return None

    helix_map = _load_helix_items_by_merge_key_cached(helix_path, helix_mtime_ns)
    if not helix_map:
        return None

    official_frames = build_helix_official_export_frames(
        export_df, helix_items_by_merge_key=helix_map
    )
    if official_frames is None:
        return None

    official_df, raw_df = official_frames
    sheets: list[tuple[str, pd.DataFrame]] = [("Issues oficial", official_df)]
    if isinstance(raw_df, pd.DataFrame) and not raw_df.empty:
        sheets.append(("Helix raw", raw_df))

    return dfs_to_excel_bytes(
        sheets,
        include_index=False,
        hyperlink_columns_by_sheet={
            "Issues oficial": [("ID de la Incidencia", "__item_url__")],
            "Helix raw": [("ID de la Incidencia", "__item_url__")],
        },
    )


def _render_issues_download_button(
    export_df: pd.DataFrame,
    *,
    key_prefix: str,
    settings: Settings | None,
    helix_only: bool = False,
) -> None:
    if export_df is None or export_df.empty:
        download_button_for_df(
            export_df,
            label="Excel",
            key=f"{key_prefix}::download_csv",
            spec=CsvDownloadSpec(filename_prefix="issues_filtradas"),
            suffix="issues",
            disabled=True,
            width="stretch",
        )
        return

    if not helix_only:
        export_sig = _issues_export_signature(export_df, helix_path="", helix_mtime_ns=-1)
        sig_key = f"{key_prefix}::jira_export_sig"
        prepared_key = f"{key_prefix}::jira_export_prepared"
        if str(st.session_state.get(sig_key) or "") != export_sig:
            st.session_state[sig_key] = export_sig
            st.session_state[prepared_key] = False

        if not bool(st.session_state.get(prepared_key, False)):
            if st.button(
                "Preparar Excel",
                key=f"{key_prefix}::prepare_excel_jira",
                type="secondary",
                width="stretch",
                help=(
                    "Genera el Excel bajo demanda para mantener la vista de Issues "
                    "fluida en alcance Jira."
                ),
            ):
                xlsx_probe = _cached_standard_issues_export_xlsx(export_df)
                st.session_state[prepared_key] = bool(xlsx_probe)
                st.rerun()
            return

        xlsx_bytes = _cached_standard_issues_export_xlsx(export_df)
        if xlsx_bytes is None:
            download_button_for_df(
                export_df,
                label="Excel",
                key=f"{key_prefix}::download_csv",
                spec=CsvDownloadSpec(filename_prefix="issues_filtradas"),
                suffix="issues",
                disabled=False,
                width="stretch",
            )
            return

        st.download_button(
            label="Excel",
            data=xlsx_bytes,
            file_name=build_download_filename("issues_filtradas", suffix="issues", ext="xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}::download_csv",
            disabled=False,
            width="stretch",
            help="Exporta el dataset filtrado completo (Jira/mixto) en formato Excel.",
        )
        return

    helix_path, helix_mtime_ns = _helix_data_path_and_mtime(settings)
    official_input_df = _official_export_input_df(export_df)
    export_sig = _issues_export_signature(
        official_input_df, helix_path=helix_path, helix_mtime_ns=helix_mtime_ns
    )
    sig_key = f"{key_prefix}::helix_export_sig"
    prepared_key = f"{key_prefix}::helix_export_prepared"
    if str(st.session_state.get(sig_key) or "") != export_sig:
        st.session_state[sig_key] = export_sig
        st.session_state[prepared_key] = False

    if not bool(st.session_state.get(prepared_key, False)):
        if st.button(
            "Preparar Excel",
            key=f"{key_prefix}::prepare_excel_helix",
            type="secondary",
            width="stretch",
            help="Genera el Excel oficial Helix bajo demanda para acelerar la carga de la pantalla.",
        ):
            xlsx_probe = _cached_helix_issues_export_xlsx(
                official_input_df,
                helix_path=helix_path,
                helix_mtime_ns=helix_mtime_ns,
            )
            if xlsx_probe is None:
                # Fallback path (non-official export) stays immediate.
                st.session_state[prepared_key] = False
            else:
                st.session_state[prepared_key] = True
            st.rerun()
        return

    xlsx_bytes = _cached_helix_issues_export_xlsx(
        official_input_df,
        helix_path=helix_path,
        helix_mtime_ns=helix_mtime_ns,
    )
    if xlsx_bytes is None:
        download_button_for_df(
            export_df,
            label="Excel",
            key=f"{key_prefix}::download_csv",
            spec=CsvDownloadSpec(filename_prefix="issues_filtradas"),
            suffix="issues",
            disabled=False,
            width="stretch",
        )
        return

    st.download_button(
        label="Excel",
        data=xlsx_bytes,
        file_name=build_download_filename("issues_filtradas", suffix="issues", ext="xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}::download_csv",
        disabled=False,
        width="stretch",
        help="Incluye hoja oficial (columnas estilo Excel de referencia) y hoja raw Helix.",
    )


def _issues_export_signature(
    export_df: pd.DataFrame, *, helix_path: str, helix_mtime_ns: int
) -> str:
    digest = _cached_export_df_digest(export_df)
    return f"{helix_path}|{helix_mtime_ns}|{len(export_df) if isinstance(export_df, pd.DataFrame) else 0}|{digest}"


@st.cache_data(
    show_spinner=False,
    max_entries=64,
    hash_funcs={pd.DataFrame: streamlit_cache_df_hash},
)
def _cached_export_df_digest(export_df: pd.DataFrame) -> str:
    if export_df is None or export_df.empty:
        return "empty"
    # Table export shape is flat (no nested lists), so pandas hashing is cheap and stable enough.
    try:
        hashed = pd.util.hash_pandas_object(export_df, index=True)
        digest = str(int(hashed.sum()))
    except Exception:
        digest = str(abs(hash(export_df.to_json(date_format="iso", orient="split"))))
    return digest


def _is_helix_only_scope(df: pd.DataFrame) -> bool:
    if df is None or df.empty or "source_type" not in df.columns:
        return False
    vals = df["source_type"].fillna("").astype(str).str.strip().str.lower().unique().tolist()
    vals = [v for v in vals if v]
    return bool(vals) and all(v == "helix" for v in vals)


def _official_export_input_df(export_df: pd.DataFrame) -> pd.DataFrame:
    if export_df is None or export_df.empty:
        return pd.DataFrame()
    needed = [
        "key",
        "summary",
        "status",
        "type",
        "priority",
        "created",
        "updated",
        "resolved",
        "url",
        "country",
        "source_type",
        "source_id",
    ]
    cols = [c for c in needed if c in export_df.columns]
    return export_df[cols].copy(deep=False)


@lru_cache(maxsize=8)
def _issues_view_toggle_css(scope_key: str) -> str:
    return f"""
    <style>
      .st-key-{scope_key} .stButton > button {{
        min-height: 2.15rem !important;
        padding: 0.35rem 0.78rem !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        border: 1px solid var(--bbva-tab-soft-border) !important;
        background: var(--bbva-tab-soft-bg) !important;
        color: var(--bbva-tab-soft-text) !important;
      }}
      .st-key-{scope_key} .stButton > button[kind="primary"] {{
        border-color: var(--bbva-tab-active-border) !important;
        background: var(--bbva-tab-active-bg) !important;
        color: var(--bbva-tab-active-text) !important;
      }}
      .st-key-{scope_key} .stButton > button * {{
        color: inherit !important;
        fill: currentColor !important;
      }}
    </style>
    """


def _inject_issues_view_toggle_css(*, scope_key: str) -> None:
    """Scoped style for Issues Cards/Tabla toggle buttons."""
    st.markdown(_issues_view_toggle_css(scope_key), unsafe_allow_html=True)


@lru_cache(maxsize=8)
def _issues_sort_export_css(scope_key: str) -> str:
    return f"""
    <style>
      .st-key-{scope_key} [data-testid="stHorizontalBlock"] {{
        gap: 0.72rem !important;
        align-items: end !important;
      }}
      .st-key-{scope_key} .stDownloadButton {{
        width: 100% !important;
        display: flex;
        justify-content: flex-end;
        padding-right: 0.28rem;
        box-sizing: border-box;
      }}
      .st-key-{scope_key} .stDownloadButton > button {{
        margin-left: auto !important;
      }}
      .st-key-{scope_key} [class*="st-key-"] [data-testid="stToggle"] {{
        display: flex;
        justify-content: flex-end;
        margin-right: 0.12rem;
      }}
    </style>
    """


def _inject_issues_sort_export_css(*, scope_key: str) -> None:
    """Scoped style for sort/export container alignment."""
    st.markdown(_issues_sort_export_css(scope_key), unsafe_allow_html=True)


def render_issues_section(
    dff: pd.DataFrame,
    *,
    title: str = "Issues",
    key_prefix: str = "issues",
    settings: Settings | None = None,
) -> None:
    """Render the Issues section with:
    - Default view: Cards
    - Table always includes all filtered issues
    - Cards are capped for render performance on large datasets
    - CSV download always enabled (both Cards & Table), using the Table export format
    """
    if title:
        st.markdown(f"### {title}")

    with st.container(border=True, key=f"{key_prefix}_issues_shell"):
        section_start_ts = perf_counter()
        perf_ms: dict[str, float] = {}

        filters_start_ts = perf_counter()
        helix_path, helix_mtime_ns = _helix_data_path_and_mtime(settings)
        dff_show_raw = _cached_prepare_issues_base_df(
            dff,
            helix_path=helix_path,
            helix_mtime_ns=helix_mtime_ns,
        )
        sort_col, sort_asc = _ensure_shared_sort_state(dff_show_raw, key_prefix=key_prefix)
        dff_like = _apply_shared_like_filter(dff_show_raw, sort_col=sort_col, key_prefix=key_prefix)
        dff_show = _apply_shared_sort(dff_like, sort_col=sort_col, sort_asc=sort_asc)

        # Tabla visible puede incluir descripción; Excel se mantiene liviano sin ese campo.
        table_df = _cached_make_table_export_df(dff_show)
        export_df = table_df.copy(deep=False)
        perf_ms["filters"] = _elapsed_ms(filters_start_ts)

        # Compact toolbar: top row for view toggle + count.
        view_key = f"{key_prefix}::view_mode"
        if str(st.session_state.get(view_key) or "").strip() not in {"Cards", "Tabla"}:
            st.session_state[view_key] = "Cards"
        view = str(st.session_state.get(view_key) or "Cards")
        total_filtered = 0 if table_df is None else int(len(table_df))
        page_size = min(CARDS_PAGE_SIZE, MAX_CARDS_RENDER)

        cards_page_key = f"{key_prefix}::cards_page"
        cards_page = int(st.session_state.get(cards_page_key, 1) or 1)
        cards_page, cards_start_idx, cards_end_idx, cards_total_pages = _cards_pagination_window(
            total_rows=int(len(dff_show)),
            page_size=page_size,
            page=cards_page,
        )
        st.session_state[cards_page_key] = cards_page
        cards_slice = (
            dff_show.iloc[cards_start_idx:cards_end_idx].copy(deep=False)
            if view == "Cards"
            else pd.DataFrame()
        )
        cards_df = (
            _cached_prepare_cards_df(cards_slice, max_cards=page_size, preserve_order=True)
            if view == "Cards"
            else pd.DataFrame()
        )

        table_page_key = f"{key_prefix}::table_page"
        table_page = int(st.session_state.get(table_page_key, 1) or 1)
        table_page, table_start_idx, table_end_idx, table_total_pages = _cards_pagination_window(
            total_rows=total_filtered,
            page_size=page_size,
            page=table_page,
        )
        st.session_state[table_page_key] = table_page
        table_slice = (
            table_df.iloc[table_start_idx:table_end_idx].copy(deep=False)
            if view == "Tabla"
            else pd.DataFrame()
        )

        top_left, top_right = st.columns([2.2, 1.0], gap="small")
        with top_left:
            if view == "Cards" and total_filtered > 0:
                st.caption(
                    f"Mostrando {cards_start_idx + 1:,}-{cards_end_idx:,} de {total_filtered:,} issues filtradas"
                )
            elif view == "Tabla" and total_filtered > 0:
                st.caption(
                    f"Mostrando {table_start_idx + 1:,}-{table_end_idx:,} de {total_filtered:,} issues filtradas"
                )
            else:
                st.caption(f"{total_filtered:,} issues filtradas")
        with top_right:
            toggle_scope = f"{key_prefix}_view_toggle"
            _inject_issues_view_toggle_css(scope_key=toggle_scope)
            with st.container(key=toggle_scope):
                c_cards, c_table = st.columns(2, gap="small")
                c_cards.button(
                    "Cards",
                    key=f"{view_key}::cards_btn",
                    type="primary" if view == "Cards" else "secondary",
                    width="stretch",
                    on_click=_set_issues_view,
                    args=(view_key, "Cards"),
                )
                c_table.button(
                    "Tabla",
                    key=f"{view_key}::table_btn",
                    type="primary" if view == "Tabla" else "secondary",
                    width="stretch",
                    on_click=_set_issues_view,
                    args=(view_key, "Tabla"),
                )

        # Independent bar below Cards/Tabla: sort controls (left) + Asc/Excel (right), aligned.
        sort_export_scope = f"{key_prefix}_sort_export"
        _inject_issues_sort_export_css(scope_key=sort_export_scope)
        exports_start_ts = perf_counter()
        with st.container(border=True, key=sort_export_scope):
            left, right = st.columns([2.2, 1.25], gap="small")
            with left:
                _render_shared_sort_controls(dff_show_raw, key_prefix=key_prefix)
            with right:
                _, controls_col = st.columns([0.55, 1.45], gap="small")
                with controls_col:
                    toggle_col, btn_col = st.columns([0.92, 1.0], gap="small")
                    with toggle_col:
                        _render_sort_direction_control(key_prefix=key_prefix)
                    with btn_col:
                        _render_issues_download_button(
                            export_df,
                            key_prefix=key_prefix,
                            settings=settings,
                            helix_only=_is_helix_only_scope(dff_show),
                        )
        perf_ms["exports"] = _elapsed_ms(exports_start_ts)

        if dff_show.empty:
            perf_ms["total"] = _elapsed_ms(section_start_ts)
            _render_issues_perf_footer(
                key_prefix=key_prefix,
                view=view,
                metrics_ms=perf_ms,
            )
            st.info("No hay issues para mostrar con los filtros actuales.")
            return

        if view == "Cards":
            cards_start_ts = perf_counter()
            render_issue_cards(
                cards_slice,
                max_cards=len(cards_df),
                title="",
                settings=settings,
                prepared_df=cards_df,
            )
            _render_pager_shell(
                shell_key=f"{key_prefix}_cards_pager_shell",
                page_key=cards_page_key,
                page=cards_page,
                total_pages=cards_total_pages,
                start_idx=cards_start_idx,
                end_idx=cards_end_idx,
                total_rows=total_filtered,
                prev_button_key=f"{key_prefix}::cards_prev",
                next_button_key=f"{key_prefix}::cards_next",
            )
            perf_ms["cards"] = _elapsed_ms(cards_start_ts)
            perf_ms["total"] = _elapsed_ms(section_start_ts)
            _render_issues_perf_footer(
                key_prefix=key_prefix,
                view=view,
                metrics_ms=perf_ms,
            )
            return

        table_start_ts = perf_counter()
        render_issue_table(
            table_slice,
            settings=settings,
            table_key=f"{key_prefix}::issues_table_grid",
            preserve_order=True,
            sort_state_prefix=key_prefix,
        )
        _render_pager_shell(
            shell_key=f"{key_prefix}_table_pager_shell",
            page_key=table_page_key,
            page=table_page,
            total_pages=table_total_pages,
            start_idx=table_start_idx,
            end_idx=table_end_idx,
            total_rows=total_filtered,
            prev_button_key=f"{key_prefix}::table_prev",
            next_button_key=f"{key_prefix}::table_next",
        )
        perf_ms["table"] = _elapsed_ms(table_start_ts)
        perf_ms["total"] = _elapsed_ms(section_start_ts)
        _render_issues_perf_footer(
            key_prefix=key_prefix,
            view=view,
            metrics_ms=perf_ms,
        )


def render_issues_tab(
    dff: pd.DataFrame | None = None,
    *,
    key_prefix: str = "issues_tab",
    settings: Settings | None = None,
) -> None:
    """
    Issues tab:
    - Consume el dataframe ya filtrado por el dashboard (single source of truth).
    - Sin filtros locales para evitar doble cómputo/incoherencias entre tabs.
    """
    dff_filtered = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    if dff_filtered.empty:
        st.info("No hay datos para mostrar.")
        return

    # Render sección (export + cards/tabla)
    render_issues_section(dff_filtered, title="", key_prefix=key_prefix, settings=settings)
