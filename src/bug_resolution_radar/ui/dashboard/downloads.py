# bug_resolution_radar/ui/dashboard/downloads.py
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence

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


def _build_filename(prefix: str, *, suffix: str = "", ext: str = "csv") -> str:
    pref = _safe_filename(prefix)
    suf = _safe_filename(suffix) if suffix else ""
    ts = _timestamp()
    dot_ext = (ext or "").strip().lstrip(".") or "txt"
    return f"{pref}{'_' + suf if suf else ''}_{ts}.{dot_ext}"


def df_to_csv_bytes(
    df: pd.DataFrame, *, include_index: bool = False, encoding: str = "utf-8"
) -> bytes:
    """Convert DataFrame to CSV bytes with safe defaults.

    - Dates are serialized by pandas; keep it simple and consistent.
    """
    if df is None:
        df = pd.DataFrame()
    csv: str = df.to_csv(index=include_index)
    return csv.encode(encoding, errors="replace")


def download_button_for_df(
    df: pd.DataFrame,
    *,
    label: str = "⬇️ Descargar CSV",
    key: str = "download_csv",
    spec: Optional[CsvDownloadSpec] = None,
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

    csv_spec = spec or CsvDownloadSpec()

    fname = _build_filename(csv_spec.filename_prefix, suffix=suffix, ext="csv")

    csv_bytes = df_to_csv_bytes(
        df, include_index=csv_spec.include_index, encoding=csv_spec.encoding
    )

    st.download_button(
        label=label,
        data=csv_bytes,
        file_name=fname,
        mime=csv_spec.mime,
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


def make_table_export_df(
    df: pd.DataFrame, *, preferred_cols: Optional[Iterable[str]] = None
) -> pd.DataFrame:
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


def fig_to_html_bytes(fig: Any) -> bytes:
    if fig is None:
        return b""
    to_html = getattr(fig, "to_html", None)
    if not callable(to_html):
        return b""
    try:
        html_doc = to_html(include_plotlyjs="cdn", full_html=True)
    except Exception:
        return b""
    return str(html_doc).encode("utf-8", errors="replace")


def figures_to_html_bytes(
    figures: Sequence[Any],
    *,
    title: str = "Export",
    subtitles: Optional[Sequence[str]] = None,
) -> bytes:
    """Build a single HTML document from multiple Plotly figures."""
    if not figures:
        return b""

    caps = list(subtitles or [])
    blocks: list[str] = []
    for i, fig in enumerate(figures):
        to_html = getattr(fig, "to_html", None)
        if not callable(to_html):
            continue
        try:
            block = to_html(include_plotlyjs=False, full_html=False)
        except Exception:
            continue
        cap = caps[i] if i < len(caps) else f"Chart {i + 1}"
        blocks.append(
            f"""
            <section class="panel">
              <h3>{html.escape(str(cap))}</h3>
              {block}
            </section>
            """
        )

    if not blocks:
        return b""

    doc = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
      body {{
        margin: 0;
        padding: 22px;
        background: #f7f9fc;
        color: #11192d;
        font-family: "Benton Sans", "Helvetica Neue", Arial, sans-serif;
      }}
      .wrap {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 16px;
      }}
      .panel {{
        background: #ffffff;
        border: 1px solid rgba(17,25,45,0.14);
        border-radius: 12px;
        padding: 12px;
      }}
      h1 {{
        margin: 0 0 10px 0;
        font-size: 1.1rem;
      }}
      h3 {{
        margin: 0 0 8px 0;
        font-size: 0.9rem;
        font-weight: 700;
        color: rgba(17,25,45,0.72);
      }}
    </style>
  </head>
  <body>
    <h1>{html.escape(title)}</h1>
    <div class="wrap">
      {''.join(blocks)}
    </div>
  </body>
</html>
"""
    return doc.encode("utf-8", errors="replace")


def _inject_minimal_export_css(scope_key: str) -> None:
    st.markdown(
        f"""
        <style>
          .st-key-{scope_key} [data-testid="column"] {{
            display: flex;
            justify-content: flex-end;
          }}
          .st-key-{scope_key} .stDownloadButton > button {{
            min-height: 1.52rem !important;
            min-width: 3.9rem !important;
            padding: 0.12rem 0.44rem !important;
            border-radius: 999px !important;
            font-size: 0.66rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.01em !important;
            line-height: 1.0 !important;
            white-space: nowrap !important;
            border: 1px solid rgba(17,25,45,0.14) !important;
            background: rgba(17,25,45,0.035) !important;
            color: rgba(17,25,45,0.70) !important;
          }}
          .st-key-{scope_key} .stDownloadButton > button:hover {{
            border-color: rgba(17,25,45,0.24) !important;
            background: rgba(17,25,45,0.06) !important;
            color: rgba(17,25,45,0.86) !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_minimal_export_actions(
    *,
    key_prefix: str,
    filename_prefix: str,
    suffix: str = "",
    csv_df: Optional[pd.DataFrame] = None,
    figure: Any = None,
    html_bytes: Optional[bytes] = None,
) -> None:
    """Minimal right-aligned exports (CSV + chart HTML when available)."""
    csv_safe = csv_df if isinstance(csv_df, pd.DataFrame) else pd.DataFrame()
    fig_html = html_bytes if html_bytes else fig_to_html_bytes(figure)

    has_csv = not csv_safe.empty
    has_html = bool(fig_html)
    if not has_csv and not has_html:
        return

    scope_key = f"{_safe_filename(key_prefix)}_mini_export"
    _inject_minimal_export_css(scope_key)

    with st.container(key=scope_key):
        if has_csv and has_html:
            _, right = st.columns([8.8, 1.2], gap="small")
            with right:
                c_csv, c_html = st.columns([1, 1], gap="small")
                with c_csv:
                    st.download_button(
                        label="CSV",
                        data=df_to_csv_bytes(csv_safe),
                        file_name=_build_filename(filename_prefix, suffix=suffix, ext="csv"),
                        mime="text/csv",
                        key=f"{key_prefix}::dl_csv_min",
                        use_container_width=False,
                    )
                with c_html:
                    st.download_button(
                        label="HTML",
                        data=fig_html,
                        file_name=_build_filename(filename_prefix, suffix=suffix, ext="html"),
                        mime="text/html",
                        key=f"{key_prefix}::dl_html_min",
                        use_container_width=False,
                    )
            return

        _, right = st.columns([9.2, 0.8], gap="small")
        with right:
            if has_csv:
                st.download_button(
                    label="CSV",
                    data=df_to_csv_bytes(csv_safe),
                    file_name=_build_filename(filename_prefix, suffix=suffix, ext="csv"),
                    mime="text/csv",
                    key=f"{key_prefix}::dl_csv_min",
                    use_container_width=False,
                )
            elif has_html:
                st.download_button(
                    label="HTML",
                    data=fig_html,
                    file_name=_build_filename(filename_prefix, suffix=suffix, ext="html"),
                    mime="text/html",
                    key=f"{key_prefix}::dl_html_min",
                    use_container_width=False,
                )
