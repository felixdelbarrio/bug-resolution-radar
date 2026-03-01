"""Issues tab orchestration and view mode selection."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

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
    dfs_to_excel_bytes,
    download_button_for_df,
    make_table_export_df,
)
from bug_resolution_radar.ui.dashboard.exports.helix_official_export import (
    build_helix_official_export_frames,
)

MAX_CARDS_RENDER = 250
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


def _sorted_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if "updated" in df.columns:
        return df.sort_values(by="updated", ascending=False)
    return df.copy()


def _set_issues_view(view_key: str, value: str) -> None:
    st.session_state[view_key] = value


def _default_issue_sort_col(df: pd.DataFrame) -> str:
    if "updated" in df.columns:
        return "updated"
    if "created" in df.columns:
        return "created"
    if "key" in df.columns:
        return "key"
    return str(df.columns[0]) if not df.empty else "updated"


def _default_sort_asc(sort_col: str) -> bool:
    return str(sort_col or "").strip().lower() not in {"updated", "created", "resolved"}


def _ensure_shared_sort_state(df: pd.DataFrame, *, key_prefix: str) -> tuple[str, bool]:
    sort_col_key = f"{key_prefix}::sort_col"
    sort_asc_key = f"{key_prefix}::sort_asc"
    default_col = _default_issue_sort_col(df)

    sort_col = str(st.session_state.get(sort_col_key) or "").strip()
    if not sort_col or sort_col not in df.columns:
        sort_col = default_col
        st.session_state[sort_col_key] = sort_col

    if sort_asc_key not in st.session_state:
        st.session_state[sort_asc_key] = _default_sort_asc(sort_col)

    sort_asc = bool(st.session_state.get(sort_asc_key, _default_sort_asc(sort_col)))
    return sort_col, sort_asc


def _sort_columns_for_controls(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty:
        return []
    preferred = [
        "updated",
        "created",
        "status",
        "priority",
        "assignee",
        "type",
        "key",
        "summary",
        "resolved",
        "country",
        "source_type",
    ]
    out: list[str] = [c for c in preferred if c in df.columns]
    extra = [c for c in df.columns if c not in out and c != "url"]
    extra_sorted = sorted(extra, key=lambda x: str(x).casefold())
    return out + extra_sorted


def _render_shared_sort_controls(df: pd.DataFrame, *, key_prefix: str) -> None:
    sort_col_key = f"{key_prefix}::sort_col"
    sort_asc_key = f"{key_prefix}::sort_asc"
    sort_col, _ = _ensure_shared_sort_state(df, key_prefix=key_prefix)
    options = _sort_columns_for_controls(df)
    if not options:
        return
    if sort_col not in options:
        options = [sort_col] + options

    c_sort, c_dir = st.columns([2.1, 1.0], gap="small")
    with c_sort:
        st.selectbox(
            "Ordenar por",
            options=options,
            key=sort_col_key,
            width="stretch",
            format_func=lambda x: _SORT_LABELS.get(str(x), str(x)),
        )
    with c_dir:
        st.toggle("Ascendente", key=sort_asc_key, width="stretch")


def _apply_shared_sort(df: pd.DataFrame, *, sort_col: str, sort_asc: bool) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    if sort_col not in df.columns:
        return df

    out = df.copy(deep=False).copy()
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

    stype = dff["source_type"].astype(str).str.strip().str.lower()
    helix_mask = stype.eq("helix")
    if not bool(helix_mask.any()):
        return dff

    helix_path, helix_mtime_ns = _helix_data_path_and_mtime(settings)
    if not helix_path:
        return dff
    desc_map = _load_helix_descriptions_cached(helix_path, helix_mtime_ns)
    if not desc_map:
        return dff

    out = dff.copy(deep=False).copy()
    if "description" not in out.columns:
        out["description"] = ""

    for idx in out.index[helix_mask]:
        key = str(out.at[idx, "key"] or "").strip().upper()
        if not key:
            continue
        source_id = (
            str(out.at[idx, "source_id"] or "").strip().lower()
            if "source_id" in out.columns
            else ""
        )
        merge_key = f"{source_id}::{key}" if source_id else key
        desc = str(desc_map.get(merge_key) or desc_map.get(key) or "").strip()
        if not desc:
            continue
        curr = str(out.at[idx, "description"] or "").strip()
        summary = str(out.at[idx, "summary"] or "").strip()
        if curr and curr != "—" and curr.lower() != summary.lower():
            continue
        out.at[idx, "description"] = desc
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

    out = dff.copy(deep=False).copy()
    if "description" not in out.columns:
        out["description"] = ""
    return out


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
            width="content",
        )
        return

    if not helix_only:
        download_button_for_df(
            export_df,
            label="Excel",
            key=f"{key_prefix}::download_csv",
            spec=CsvDownloadSpec(filename_prefix="issues_filtradas"),
            suffix="issues",
            disabled=False,
            width="content",
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
            key=f"{key_prefix}::prepare_excel",
            type="secondary",
            width="content",
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
            width="content",
        )
        return

    st.download_button(
        label="Excel",
        data=xlsx_bytes,
        file_name=build_download_filename("issues_filtradas", suffix="issues", ext="xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}::download_csv",
        disabled=False,
        width="content",
        help="Incluye hoja oficial (columnas estilo Excel de referencia) y hoja raw Helix.",
    )


def _issues_export_signature(
    export_df: pd.DataFrame, *, helix_path: str, helix_mtime_ns: int
) -> str:
    if export_df is None or export_df.empty:
        return "empty"
    # Table export shape is flat (no nested lists), so pandas hashing is cheap and stable enough.
    try:
        hashed = pd.util.hash_pandas_object(export_df, index=True)
        digest = str(int(hashed.sum()))
    except Exception:
        digest = str(abs(hash(export_df.to_json(date_format="iso", orient="split"))))
    return f"{helix_path}|{helix_mtime_ns}|{len(export_df)}|{digest}"


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


def _inject_issues_view_toggle_css(*, scope_key: str) -> None:
    """Scoped style for Issues Cards/Tabla toggle buttons."""
    st.markdown(
        f"""
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
        """,
        unsafe_allow_html=True,
    )


def _inject_issues_sort_export_css(*, scope_key: str) -> None:
    """Scoped style for sort/export container alignment."""
    st.markdown(
        f"""
        <style>
          .st-key-{scope_key} [data-testid="stHorizontalBlock"] {{
            gap: 0.72rem !important;
          }}
          .st-key-{scope_key} .stDownloadButton {{
            width: 100% !important;
            display: flex;
            justify-content: flex-end;
            padding-right: 0.55rem;
            box-sizing: border-box;
          }}
          .st-key-{scope_key} .stDownloadButton > button {{
            margin-left: auto !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


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
        dff_show_raw = _inject_helix_descriptions(_sorted_for_display(dff), settings=settings)
        dff_show_raw = _inject_missing_jira_descriptions_from_summary(dff_show_raw)
        sort_col, sort_asc = _ensure_shared_sort_state(dff_show_raw, key_prefix=key_prefix)
        dff_show = _apply_shared_sort(dff_show_raw, sort_col=sort_col, sort_asc=sort_asc)

        # Tabla visible puede incluir descripción; Excel se mantiene liviano sin ese campo.
        table_pref_cols = [
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
        table_df = make_table_export_df(dff_show, preferred_cols=table_pref_cols)
        export_df = table_df.copy(deep=False)

        # Compact toolbar: top row for view toggle + count.
        view_key = f"{key_prefix}::view_mode"
        if str(st.session_state.get(view_key) or "").strip() not in {"Cards", "Tabla"}:
            st.session_state[view_key] = "Cards"
        view = str(st.session_state.get(view_key) or "Cards")
        total_filtered = 0 if table_df is None else int(len(table_df))
        max_cards = min(int(len(dff_show)), MAX_CARDS_RENDER)
        cards_df = (
            prepare_issue_cards_df(dff_show, max_cards=max_cards, preserve_order=True)
            if view == "Cards"
            else pd.DataFrame()
        )
        shown_in_cards = int(len(cards_df)) if view == "Cards" else total_filtered

        top_left, top_right = st.columns([2.2, 1.0], gap="small")
        with top_left:
            if view == "Cards" and shown_in_cards != total_filtered:
                st.caption(f"{shown_in_cards:,}/{total_filtered:,} issues filtradas")
            else:
                st.caption(f"{shown_in_cards:,} issues filtradas")
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

        # Independent bar below Cards/Tabla: sort controls (left) + Excel (right), aligned.
        sort_export_scope = f"{key_prefix}_sort_export"
        _inject_issues_sort_export_css(scope_key=sort_export_scope)
        with st.container(border=True, key=sort_export_scope):
            left, right = st.columns([2.35, 1.0], gap="small")
            with left:
                _render_shared_sort_controls(dff_show_raw, key_prefix=key_prefix)
            with right:
                _, btn_slot = st.columns([1.0, 0.001], gap="small")
                with btn_slot:
                    _render_issues_download_button(
                        export_df,
                        key_prefix=key_prefix,
                        settings=settings,
                        helix_only=_is_helix_only_scope(dff_show),
                    )

        if dff_show.empty:
            st.info("No hay issues para mostrar con los filtros actuales.")
            return

        if view == "Cards":
            if len(dff_show) > MAX_CARDS_RENDER:
                st.caption(
                    f"Vista Cards mostrando {max_cards}/{len(dff_show)}. "
                    "Usa Tabla para ver todos los resultados."
                )
            render_issue_cards(
                dff_show,
                max_cards=len(cards_df),
                title="",
                settings=settings,
                prepared_df=cards_df,
            )
            return

        render_issue_table(
            table_df,
            settings=settings,
            table_key=f"{key_prefix}::issues_table_grid",
            preserve_order=True,
            sort_state_prefix=key_prefix,
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
