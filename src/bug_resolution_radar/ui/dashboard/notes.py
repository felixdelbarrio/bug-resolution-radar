from __future__ import annotations

import pandas as pd
import streamlit as st

from bug_resolution_radar.notes import NotesStore


def render_notes_tab(*, dff: pd.DataFrame, notes: NotesStore) -> None:
    """
    Tab de notas (locales).
    - Usa el DF ya filtrado (dff)
    - Persiste en NotesStore
    """
    st.markdown("### 🗒️ Notas")

    if dff is None or dff.empty or "key" not in dff.columns:
        st.info("No hay issues disponibles para notas.")
        return

    # Lista estable (ordenada) para UX
    keys = dff["key"].dropna().astype(str).unique().tolist()
    keys = sorted(keys)

    issue_key = st.selectbox("Issue", keys, key="notes_issue_key")

    current = notes.get(issue_key) or ""
    new_note = st.text_area("Nota (local)", value=current, height=140, key="notes_text")

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("💾 Guardar nota", key="notes_save_btn", use_container_width=True):
            notes.set(issue_key, new_note)
            notes.save()
            st.success("Nota guardada localmente.")
    with c2:
        st.caption("Estas notas se guardan en tu máquina (no se suben a ningún servidor).")
