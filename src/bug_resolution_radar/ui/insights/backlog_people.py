# src/bug_resolution_radar/ui/insights/backlog_people.py
from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)
from bug_resolution_radar.ui.insights.helpers import (
    as_naive_utc,
    build_issue_lookup,
    col_exists,
    open_only,
    pct,
    priority_weight,
    risk_label,
    safe_df,
    status_bucket,
)


# -------------------------
# Acciones (sincroniza filtros globales + salto a Issues)
# -------------------------
def _apply_filters_base_for_assignee(assignee: str) -> None:
    st.session_state[FILTER_ASSIGNEE_KEY] = [assignee] if assignee else []
    # Nota: por decisión de producto, NO filtramos por type aquí (tipo eliminado de filtros)
    st.session_state[FILTER_PRIORITY_KEY] = []


def _jump_to_assignee_status(assignee: str, status: str) -> None:
    _apply_filters_base_for_assignee(assignee)
    st.session_state[FILTER_STATUS_KEY] = [status] if status else []
    st.session_state["__action_mode"] = True
    st.session_state["__action_assignee"] = assignee or ""
    st.session_state["__action_status"] = status or ""
    st.session_state["__jump_to_tab"] = "issues"


def _jump_assignee_highest_high(assignee: str) -> None:
    _apply_filters_base_for_assignee(assignee)
    st.session_state[FILTER_STATUS_KEY] = []
    st.session_state[FILTER_PRIORITY_KEY] = ["Highest", "High"]
    st.session_state["__action_mode"] = True
    st.session_state["__action_assignee"] = assignee or ""
    st.session_state["__action_status"] = "Highest/High"
    st.session_state["__jump_to_tab"] = "issues"


def _jump_assignee_blocked(assignee: str) -> None:
    _apply_filters_base_for_assignee(assignee)
    st.session_state[FILTER_PRIORITY_KEY] = []
    st.session_state[FILTER_STATUS_KEY] = ["Blocked"]
    st.session_state["__action_mode"] = True
    st.session_state["__action_assignee"] = assignee or ""
    st.session_state["__action_status"] = "Blocked"
    st.session_state["__jump_to_tab"] = "issues"


# -------------------------
# Render
# -------------------------
def render_backlog_people_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
    """
    Tab: Concentración de backlog por asignado (abiertas)
    - Expander por persona
    - Dentro: desglose por estado (bullets) + KPIs + acciones rápidas
    - Extra: Top 3 más antiguas (si hay created)
    """
    st.markdown("### 👤 Backlog por persona (abiertas)")

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    open_df = open_only(dff)
    if open_df.empty or not col_exists(open_df, "assignee"):
        st.info(
            "No hay incidencias abiertas (o no hay columna `assignee`) con los filtros actuales."
        )
        return

    df2 = open_df.copy()
    df2["assignee"] = df2["assignee"].fillna("(sin asignar)").astype(str)

    if col_exists(df2, "status"):
        df2["status"] = normalize_text_col(df2["status"], "(sin estado)")
    else:
        df2["status"] = "(sin estado)"

    if col_exists(df2, "priority"):
        df2["priority"] = normalize_text_col(df2["priority"], "(sin priority)")
    else:
        df2["priority"] = "(sin priority)"

    # Aging
    has_created = col_exists(df2, "created") and pd.api.types.is_datetime64_any_dtype(
        df2["created"]
    )
    if has_created:
        now = pd.Timestamp.utcnow().tz_localize(None)
        created_naive = as_naive_utc(df2["created"])
        df2["age_days"] = (now - created_naive).dt.total_seconds() / 86400.0
        df2["age_days"] = df2["age_days"].clip(lower=0.0)
    else:
        df2["age_days"] = pd.NA

    total_open = int(len(df2))
    counts = df2.groupby("assignee").size().sort_values(ascending=False).head(12)

    key_to_url, key_to_meta = build_issue_lookup(df2, settings=settings)

    for assignee, n in counts.items():
        n_int = int(n)
        hdr = f"**{assignee}** · **{n_int}** abiertas · **{pct(n_int, total_open):.1f}%**"

        with st.expander(hdr, expanded=False):
            sub = df2[df2["assignee"] == assignee].copy()

            # ---------------------------------
            # 1) Bullets: estados (conteo)
            # ---------------------------------
            st_counts = sub["status"].value_counts()
            st.markdown("**Backlog por estado (bullets)**")
            for st_name, c in st_counts.items():
                st.markdown(f"- **{st_name}** · {int(c)}")

            # ---------------------------------
            # 2) KPIs riesgo (flow + criticidad)
            # ---------------------------------
            sub["__bucket"] = sub["status"].astype(str).map(status_bucket)
            bcounts = sub["__bucket"].value_counts()
            b_entrada = int(bcounts.get("entrada", 0))
            b_curso = int(bcounts.get("en_curso", 0))
            b_salida = int(bcounts.get("salida", 0))
            b_bloq = int(bcounts.get("bloqueado", 0))

            flow_risk_pct = pct(b_entrada + b_bloq, n_int)

            sub["__w"] = sub["priority"].astype(str).map(priority_weight)
            w_total = float(sub["__w"].sum()) if n_int else 0.0
            w_bad = (
                float(sub.loc[sub["__bucket"].isin(["entrada", "bloqueado"]), "__w"].sum())
                if n_int
                else 0.0
            )
            crit_risk_pct = (w_bad / w_total * 100.0) if w_total > 0 else 0.0

            risk_score = 0.6 * flow_risk_pct + 0.4 * crit_risk_pct
            risk_txt = risk_label(risk_score)

            dom_status = str(st_counts.index[0]) if not st_counts.empty else ""

            # ---------------------------------
            # 3) Acciones rápidas (sincroniza filtros)
            # ---------------------------------
            cA, cB, cC = st.columns([1.2, 1.2, 2.6])
            with cA:
                st.button(
                    "🎯 Abrir backlog (estado dominante)",
                    key=f"assignee_jump::{assignee}",
                    use_container_width=True,
                    on_click=_jump_to_assignee_status,
                    args=(assignee, dom_status),
                    help="Sincroniza filtros: asignado + estado dominante.",
                )
            with cB:
                st.button(
                    "🔥 Solo Highest/High",
                    key=f"assignee_high::{assignee}",
                    use_container_width=True,
                    on_click=_jump_assignee_highest_high,
                    args=(assignee,),
                    help="Filtro: assignee + priority Highest/High.",
                )
            with cC:
                st.button(
                    "⛔ Solo bloqueadas",
                    key=f"assignee_blocked::{assignee}",
                    use_container_width=True,
                    on_click=_jump_assignee_blocked,
                    args=(assignee,),
                    help="Filtro: assignee + status=Blocked.",
                )

            # KPIs
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.metric("Riesgo (flow+criticidad)", f"{risk_txt}")
                st.caption(f"Flow {flow_risk_pct:.0f}% · Crit {crit_risk_pct:.0f}%")
            with k2:
                st.metric("Empuje a salida", f"{pct(b_salida, n_int):.0f}%")
                st.caption("Más alto suele indicar mejor throughput.")
            with k3:
                st.metric("Bloqueadas", f"{b_bloq}")
                st.caption("Bloqueo = colas ocultas.")
            with k4:
                if has_created and sub["age_days"].notna().any():
                    p90 = float(sub["age_days"].quantile(0.90))
                    st.metric("Aging P90", f"{p90:.0f}d")
                    st.caption("Si sube: riesgo SLA/deuda.")
                else:
                    st.metric("Aging P90", "-")
                    st.caption("Tip: incluye `created` (datetime).")

            # ---------------------------------
            # 4) Recomendación operativa
            # ---------------------------------
            st.markdown("**Recomendación operativa (acción)**")
            recs: List[str] = []
            if b_bloq > 0:
                recs.append("Ataca bloqueadas primero: desbloquear 1–3 items suele liberar flujo.")
            if crit_risk_pct >= 55.0:
                recs.append(
                    "Criticidad atrapada en Entrada/Bloqueado: fija dueños/fechas y prioriza Highest/High."
                )
            if flow_risk_pct >= 60.0:
                recs.append(
                    "Entrada saturada: triage agresivo (duplicados/out-of-scope) y limita WIP nuevo."
                )
            if b_curso > 0 and b_salida == 0:
                recs.append(
                    "Crea ‘push’ hacia salida: objetivo semanal de mover X items a Verify/Deploy."
                )
            if not recs:
                recs.append("Buen equilibrio: mantén WIP limitado y revisa aging semanalmente.")
            for rr in recs[:4]:
                st.markdown(f"- {rr}")

            # ---------------------------------
            # 5) Top 3 más antiguas (si hay created)
            # ---------------------------------
            if has_created and col_exists(sub, "key") and sub["age_days"].notna().any():
                st.markdown("**Top 3 más antiguas (limpieza quirúrgica)**")
                oldest = (
                    sub.dropna(subset=["age_days"]).sort_values("age_days", ascending=False).head(3)
                )

                for _, rr in oldest.iterrows():
                    k = str(rr.get("key", "") or "").strip()
                    if not k:
                        continue
                    age = float(rr.get("age_days", 0.0) or 0.0)

                    status, prio, summ = key_to_meta.get(k, ("(sin estado)", "(sin priority)", ""))
                    summ_txt = (summ or "").strip()
                    if len(summ_txt) > 90:
                        summ_txt = summ_txt[:87] + "..."

                    url = key_to_url.get(k, "")
                    if url:
                        st.markdown(
                            f"- **[{k}]({url})** · {age:.0f}d · *{status}* · *{prio}* · {summ_txt}"
                        )
                    else:
                        st.markdown(f"- **{k}** · {age:.0f}d · *{status}* · *{prio}* · {summ_txt}")

    st.caption(
        "Tip: el riesgo combina ‘atasco de flujo’ (Entrada/Bloqueadas) + ‘criticidad atrapada’ (Highest/High sin avanzar)."
    )
