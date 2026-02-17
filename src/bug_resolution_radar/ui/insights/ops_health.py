# src/bug_resolution_radar/ui/insights/ops_health.py
from __future__ import annotations

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.insights.helpers import (
    as_naive_utc,
    build_issue_lookup,
    col_exists,
    open_only,
    safe_df,
)


def render_ops_health_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
    """
    Tab: Salud operativa (operational quick insights)
      - KPIs resumen (issues filtradas, abiertas, prioridad dominante)
      - Top 10 abiertas más antiguas (bullets + key clickable + status/priority/summary)
    """
    st.markdown("### 🛠️ Salud operativa")

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    open_df = open_only(dff)

    # -------------------------
    # KPIs resumen
    # -------------------------
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Issues (filtradas)", int(len(dff)))
    with c2:
        st.metric("Abiertas (filtradas)", int(len(open_df)))
    with c3:
        if col_exists(open_df, "priority") and not open_df.empty:
            pr = normalize_text_col(open_df["priority"], "(sin priority)")
            top = pr.value_counts().head(1)
            top_txt = f"{top.index[0]} · {int(top.iloc[0])}" if not top.empty else "-"
            st.metric("Prioridad dominante", top_txt)
        else:
            st.metric("Prioridad dominante", "-")

    st.markdown("---")

    # -------------------------
    # Top 10 abiertas más antiguas
    # -------------------------
    if open_df.empty or not (
        col_exists(open_df, "created") and pd.api.types.is_datetime64_any_dtype(open_df["created"])
    ):
        st.caption(
            "Tip: si tu ingest incluye `created` como datetime, aquí verás las más antiguas."
        )
        return

    tmp = open_df[open_df["created"].notna()].copy()
    if tmp.empty:
        st.caption("No hay `created` válidas para calcular antigüedad.")
        return

    now = pd.Timestamp.utcnow().tz_localize(None)
    created_naive = as_naive_utc(tmp["created"])
    tmp["age_days"] = (now - created_naive).dt.total_seconds() / 86400.0
    tmp["age_days"] = tmp["age_days"].clip(lower=0.0)

    # Orden por antigüedad (desc)
    tmp = tmp.sort_values("age_days", ascending=False).head(10)

    # Lookup (links + meta)
    key_to_url, key_to_meta = build_issue_lookup(tmp, settings=settings)

    with st.container(border=True):
        st.markdown("#### 🧓 Top 10 abiertas más antiguas (según filtros)")
        for _, rr in tmp.iterrows():
            k = str(rr.get("key", "") or "").strip()
            if not k:
                continue

            age = float(rr.get("age_days", 0.0) or 0.0)
            status, prio, summ = key_to_meta.get(k, ("(sin estado)", "(sin priority)", ""))

            summ_txt = (summ or "").strip()
            if len(summ_txt) > 120:
                summ_txt = summ_txt[:117] + "..."

            url = key_to_url.get(k, "")
            if url:
                st.markdown(f"- **[{k}]({url})** · {age:.0f}d · *{status}* · *{prio}* · {summ_txt}")
            else:
                st.markdown(f"- **{k}** · {age:.0f}d · *{status}* · *{prio}* · {summ_txt}")
