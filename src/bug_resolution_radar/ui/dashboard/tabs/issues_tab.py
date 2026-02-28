"""Issues tab orchestration and view mode selection."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema_helix import HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.ui.components.issues import (
    prepare_issue_cards_df,
    render_issue_cards,
    render_issue_table,
)
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
CARDS_PAGE_SIZE_OPTIONS = (20, 40, 60, 100)
DEFAULT_CARDS_PAGE_SIZE = 40


def _sorted_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if "updated" in df.columns:
        return df.sort_values(by="updated", ascending=False)
    return df.copy()


def _set_issues_view(view_key: str, value: str) -> None:
    st.session_state[view_key] = value


def _paginate_cards_df(
    cards_df: pd.DataFrame,
    *,
    key_prefix: str,
) -> tuple[pd.DataFrame, int, int]:
    if cards_df is None or cards_df.empty:
        return pd.DataFrame(), 0, 0

    page_size_key = f"{key_prefix}::cards_page_size"
    page_key = f"{key_prefix}::cards_page"

    if int(st.session_state.get(page_size_key) or 0) not in CARDS_PAGE_SIZE_OPTIONS:
        st.session_state[page_size_key] = DEFAULT_CARDS_PAGE_SIZE

    total = int(len(cards_df))
    page_size = int(st.session_state.get(page_size_key) or DEFAULT_CARDS_PAGE_SIZE)
    page_size = max(1, page_size)
    total_pages = max(1, int(math.ceil(float(total) / float(page_size))))
    current_page = int(st.session_state.get(page_key) or 1)
    current_page = min(max(1, current_page), total_pages)
    st.session_state[page_key] = current_page

    with st.container(key=f"{key_prefix}::cards_pager"):
        c_size, c_page, c_info = st.columns([1.05, 1.0, 1.4], gap="small")
        with c_size:
            st.selectbox(
                "Cards por página",
                options=list(CARDS_PAGE_SIZE_OPTIONS),
                key=page_size_key,
                label_visibility="collapsed",
            )
        # Recalculate in case page size changed in this rerun.
        page_size = int(st.session_state.get(page_size_key) or DEFAULT_CARDS_PAGE_SIZE)
        page_size = max(1, page_size)
        total_pages = max(1, int(math.ceil(float(total) / float(page_size))))
        if int(st.session_state.get(page_key) or 1) > total_pages:
            st.session_state[page_key] = total_pages
        with c_page:
            st.number_input(
                "Página",
                min_value=1,
                max_value=total_pages,
                step=1,
                key=page_key,
                label_visibility="collapsed",
            )
        current_page = int(st.session_state.get(page_key) or 1)
        start = int((current_page - 1) * page_size)
        end = min(total, start + page_size)
        with c_info:
            st.caption(f"Mostrando {start + 1:,}-{end:,} de {total:,} cards")

    return cards_df.iloc[start:end].copy(deep=False), current_page, total_pages


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


@st.cache_data(show_spinner=False, max_entries=24)
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
        dff_show = _sorted_for_display(dff)

        # CSV export always uses the "table-like" dataframe
        export_df = make_table_export_df(dff_show)

        # Compact toolbar: CSV + count + view mode (same visual language as top tabs)
        view_key = f"{key_prefix}::view_mode"
        if str(st.session_state.get(view_key) or "").strip() not in {"Cards", "Tabla"}:
            st.session_state[view_key] = "Cards"
        view = str(st.session_state.get(view_key) or "Cards")
        total_filtered = 0 if export_df is None else int(len(export_df))
        max_cards = min(int(len(dff_show)), MAX_CARDS_RENDER)
        cards_df = (
            prepare_issue_cards_df(dff_show, max_cards=max_cards)
            if view == "Cards"
            else pd.DataFrame()
        )
        shown_in_cards = int(len(cards_df)) if view == "Cards" else total_filtered

        # Keep same grid as filters (Estado | Priority | Asignado) for strict visual alignment.
        left, center, right = st.columns([1.35, 1.0, 1.0], gap="small")
        with left:
            _render_issues_download_button(
                export_df,
                key_prefix=key_prefix,
                settings=settings,
                helix_only=_is_helix_only_scope(dff_show),
            )
        with center:
            if view == "Cards" and shown_in_cards != total_filtered:
                st.caption(f"{shown_in_cards:,}/{total_filtered:,} issues filtradas")
            else:
                st.caption(f"{shown_in_cards:,} issues filtradas")
        with right:
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

        if dff_show.empty:
            st.info("No hay issues para mostrar con los filtros actuales.")
            return

        if view == "Cards":
            if len(dff_show) > MAX_CARDS_RENDER:
                st.caption(
                    f"Vista Cards mostrando {max_cards}/{len(dff_show)}. "
                    "Usa Tabla para ver todos los resultados."
                )
            paged_cards_df, current_page, total_pages = _paginate_cards_df(
                cards_df,
                key_prefix=key_prefix,
            )
            if total_pages > 1:
                st.caption(f"Página {current_page}/{total_pages}")
            render_issue_cards(
                dff_show,
                max_cards=len(paged_cards_df),
                title="",
                prepared_df=paged_cards_df,
            )
            return

        render_issue_table(export_df)


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
