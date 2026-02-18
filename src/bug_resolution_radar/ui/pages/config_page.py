"""Configuration page to manage data sources and visualization preferences."""

from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import (
    Settings,
    build_source_id,
    helix_sources,
    jira_sources,
    save_settings,
    supported_countries,
    to_env_json,
)
from bug_resolution_radar.source_maintenance import (
    purge_source_cache,
    remove_helix_source_from_settings,
    remove_jira_source_from_settings,
)


def _boolish(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _trend_chart_catalog() -> List[Tuple[str, str]]:
    return [
        ("timeseries", "Evolución (últimos 90 días)"),
        ("age_buckets", "Distribución antigüedad (abiertas)"),
        ("resolution_hist", "Distribución tiempos de resolución (cerradas)"),
        ("open_priority_pie", "Issues abiertos por prioridad (pie)"),
        ("open_status_bar", "Issues por Estado (bar)"),
    ]


def _safe_update_settings(settings: Settings, update: Dict[str, Any]) -> Settings:
    allowed = set(getattr(settings.__class__, "model_fields", {}).keys())
    clean = {k: v for k, v in update.items() if k in allowed}
    return settings.model_copy(update=clean)


def _parse_csv_ids(raw: object, valid_ids: List[str]) -> List[str]:
    txt = str(raw or "").strip()
    if not txt:
        return []
    out: List[str] = []
    for x in txt.split(","):
        v = x.strip()
        if v and v in valid_ids and v not in out:
            out.append(v)
    return out


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _render_purge_stats(stats: Dict[str, int]) -> None:
    issues_removed = int(stats.get("issues_removed", 0) or 0)
    helix_items_removed = int(stats.get("helix_items_removed", 0) or 0)
    learning_scopes_removed = int(stats.get("learning_scopes_removed", 0) or 0)
    st.info(
        "Cache saneado. "
        f"Issues purgados: {issues_removed}. "
        f"Items Helix purgados: {helix_items_removed}. "
        f"Scopes de aprendizaje purgados: {learning_scopes_removed}."
    )


def _merge_purge_stats(acc: Dict[str, int], nxt: Dict[str, int]) -> Dict[str, int]:
    return {
        "issues_removed": int(acc.get("issues_removed", 0) or 0)
        + int(nxt.get("issues_removed", 0) or 0),
        "helix_items_removed": int(acc.get("helix_items_removed", 0) or 0)
        + int(nxt.get("helix_items_removed", 0) or 0),
        "learning_scopes_removed": int(acc.get("learning_scopes_removed", 0) or 0)
        + int(nxt.get("learning_scopes_removed", 0) or 0),
    }


def _is_delete_phrase_valid(value: Any) -> bool:
    return str(value or "").strip().upper() == "ELIMINAR"


def _inject_delete_zone_css() -> None:
    st.markdown(
        """
        <style>
          [class*="st-key-cfg_jira_delete_shell"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-cfg_helix_delete_shell"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 86%, #95BAFF 14%) !important;
            background:
              radial-gradient(1200px 280px at 0% 0%, color-mix(in srgb, var(--bbva-primary) 8%, transparent), transparent 55%),
              linear-gradient(155deg, color-mix(in srgb, var(--bbva-surface) 92%, #0E234C 8%), var(--bbva-surface));
            box-shadow: 0 12px 28px color-mix(in srgb, var(--bbva-text) 10%, transparent) !important;
            border-radius: var(--bbva-radius-xl) !important;
          }
          .cfg-delete-chip-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: .5rem;
            margin: .2rem 0 .4rem;
          }
          .cfg-delete-chip {
            display: inline-flex;
            align-items: center;
            gap: .4rem;
            padding: .28rem .78rem;
            border-radius: 999px;
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 74%, #8EB4FF 26%);
            background: color-mix(in srgb, var(--bbva-surface-elevated) 84%, #0D224A 16%);
            color: color-mix(in srgb, var(--bbva-text) 95%, transparent);
            font-size: .91rem;
            line-height: 1.15rem;
            font-weight: 600;
          }
          .cfg-delete-chip-dot {
            width: .46rem;
            height: .46rem;
            border-radius: 50%;
            background: color-mix(in srgb, var(--bbva-primary) 76%, #7EA8FF 24%);
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--bbva-primary) 20%, transparent);
          }
          .cfg-delete-ghost {
            border: 1px dashed var(--bbva-border);
            border-radius: var(--bbva-radius-m);
            padding: .65rem .75rem;
            color: var(--bbva-text-muted);
            background: color-mix(in srgb, var(--bbva-surface) 96%, transparent);
            margin-bottom: .25rem;
            font-size: .92rem;
          }
          .cfg-delete-counter {
            color: color-mix(in srgb, var(--bbva-text) 86%, transparent);
            margin-bottom: .2rem;
            font-size: .92rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_selected_source_chips(
    selected_source_ids: List[str], source_label_by_id: Dict[str, str]
) -> None:
    if not selected_source_ids:
        return
    chips_html = ['<div class="cfg-delete-chip-wrap">']
    for sid in selected_source_ids:
        label = source_label_by_id.get(str(sid), str(sid))
        chips_html.append(
            '<span class="cfg-delete-chip"><span class="cfg-delete-chip-dot"></span>'
            f"{escape(label)}"
            "</span>"
        )
    chips_html.append("</div>")
    st.markdown("".join(chips_html), unsafe_allow_html=True)


def _render_source_delete_container(
    *,
    section_title: str,
    source_label: str,
    selected_source_ids: List[str],
    selected_label_by_id: Dict[str, str],
    key_prefix: str,
) -> Dict[str, Any]:
    st.markdown(section_title)

    with st.container(border=True, key=f"{key_prefix}_delete_shell"):
        st.markdown("#### Zona segura de eliminación")
        st.caption(
            "La eliminación se ejecuta al pulsar Guardar configuración. "
            "El saneado de cache asociado se aplica siempre."
        )

        has_selection = bool(selected_source_ids)
        if has_selection:
            plural = "s" if len(selected_source_ids) != 1 else ""
            st.markdown(
                f'<div class="cfg-delete-counter"><strong>{len(selected_source_ids)}</strong> '
                f"fuente{plural} seleccionada{plural} desde la tabla.</div>",
                unsafe_allow_html=True,
            )
            _render_selected_source_chips(selected_source_ids, selected_label_by_id)
        else:
            st.markdown(
                f'<div class="cfg-delete-ghost">Marca en la tabla las fuentes {source_label} '
                "que quieras eliminar. Aquí aparecerán como chips country · alias.</div>",
                unsafe_allow_html=True,
            )

        confirm_target = (
            f"estas fuentes {source_label}"
            if len(selected_source_ids) != 1
            else f"esta fuente {source_label}"
        )
        confirm = st.checkbox(
            f"Confirmo que quiero eliminar {confirm_target} de forma permanente.",
            key=f"{key_prefix}_delete_confirm",
        )
        phrase = st.text_input(
            "Escribe ELIMINAR para confirmar",
            value="",
            key=f"{key_prefix}_delete_phrase",
            help="Confirmación reforzada para evitar borrados accidentales.",
        )

        phrase_ok = _is_delete_phrase_valid(phrase)
        has_partial_input = bool(has_selection or confirm or str(phrase).strip())
        armed = bool(has_selection and confirm and phrase_ok)
        valid = bool((not has_partial_input) or armed)

        if has_partial_input and not has_selection:
            st.warning(f"Selecciona al menos una fuente {source_label} para eliminar.")
        elif has_partial_input and not armed:
            st.warning(
                "Para aplicar la eliminación debes seleccionar fuentes, "
                "marcar confirmación y escribir ELIMINAR."
            )
        elif armed:
            st.success(
                f"Eliminación preparada ({len(selected_source_ids)}). "
                "Se aplicará al guardar configuración."
            )

        return {"source_ids": selected_source_ids, "armed": armed, "valid": valid}


def _rows_from_jira_settings(settings: Settings, countries: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for src in jira_sources(settings):
        country = _as_str(src.get("country"))
        if country not in countries:
            continue
        rows.append(
            {
                "__delete__": False,
                "__source_id__": _as_str(src.get("source_id")),
                "country": country,
                "alias": _as_str(src.get("alias")),
                "jql": _as_str(src.get("jql")),
            }
        )
    return rows


def _rows_from_helix_settings(settings: Settings, countries: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for src in helix_sources(settings):
        country = _as_str(src.get("country"))
        if country not in countries:
            continue
        rows.append(
            {
                "__delete__": False,
                "__source_id__": _as_str(src.get("source_id")),
                "country": country,
                "alias": _as_str(src.get("alias")),
                "base_url": _as_str(src.get("base_url")),
                "organization": _as_str(src.get("organization")),
                "browser": _as_str(src.get("browser")) or "chrome",
                "proxy": _as_str(src.get("proxy")),
                "ssl_verify": _as_str(src.get("ssl_verify")) or "true",
            }
        )
    return rows


def _normalize_jira_rows(
    df: pd.DataFrame, countries: List[str]
) -> Tuple[List[Dict[str, str]], List[str]]:
    out: List[Dict[str, str]] = []
    errors: List[str] = []
    seen: set[tuple[str, str]] = set()

    for idx, row in enumerate(df.to_dict(orient="records"), start=1):
        if _boolish(row.get("__delete__"), default=False):
            continue
        country = _as_str(row.get("country"))
        alias = _as_str(row.get("alias"))
        jql = _as_str(row.get("jql"))

        if not country and not alias and not jql:
            continue
        if country not in countries:
            errors.append(f"Jira fila {idx}: país inválido.")
            continue
        if not alias:
            errors.append(f"Jira fila {idx}: alias obligatorio.")
            continue
        if not jql:
            errors.append(f"Jira fila {idx}: JQL obligatorio.")
            continue

        dedup_key = (country, alias.lower())
        if dedup_key in seen:
            errors.append(f"Jira fila {idx}: alias duplicado para {country}.")
            continue
        seen.add(dedup_key)
        out.append({"country": country, "alias": alias, "jql": jql})

    return out, errors


def _normalize_helix_rows(
    df: pd.DataFrame, countries: List[str]
) -> Tuple[List[Dict[str, str]], List[str]]:
    out: List[Dict[str, str]] = []
    errors: List[str] = []
    seen: set[tuple[str, str]] = set()

    for idx, row in enumerate(df.to_dict(orient="records"), start=1):
        if _boolish(row.get("__delete__"), default=False):
            continue
        country = _as_str(row.get("country"))
        alias = _as_str(row.get("alias"))
        base_url = _as_str(row.get("base_url"))
        organization = _as_str(row.get("organization"))
        browser = _as_str(row.get("browser")) or "chrome"
        proxy = _as_str(row.get("proxy"))
        ssl_verify = _as_str(row.get("ssl_verify")) or "true"

        if not any([country, alias, base_url, organization, proxy]):
            continue
        if country not in countries:
            errors.append(f"Helix fila {idx}: país inválido.")
            continue
        if not alias:
            errors.append(f"Helix fila {idx}: alias obligatorio.")
            continue
        if not base_url:
            errors.append(f"Helix fila {idx}: base_url obligatorio.")
            continue
        if not organization:
            errors.append(f"Helix fila {idx}: organization obligatorio.")
            continue
        if browser not in {"chrome", "edge"}:
            errors.append(f"Helix fila {idx}: browser debe ser chrome o edge.")
            continue
        if ssl_verify not in {"true", "false"}:
            errors.append(f"Helix fila {idx}: ssl_verify debe ser true o false.")
            continue

        dedup_key = (country, alias.lower())
        if dedup_key in seen:
            errors.append(f"Helix fila {idx}: alias duplicado para {country}.")
            continue
        seen.add(dedup_key)
        out.append(
            {
                "country": country,
                "alias": alias,
                "base_url": base_url,
                "organization": organization,
                "browser": browser,
                "proxy": proxy,
                "ssl_verify": ssl_verify,
            }
        )

    return out, errors


def _selected_sources_from_editor(
    df: pd.DataFrame, *, source_type: str
) -> Tuple[List[str], Dict[str, str]]:
    selected_ids: List[str] = []
    label_by_id: Dict[str, str] = {}

    for row in df.to_dict(orient="records"):
        if not _boolish(row.get("__delete__"), default=False):
            continue
        country = _as_str(row.get("country"))
        alias = _as_str(row.get("alias"))
        sid = _as_str(row.get("__source_id__"))
        if not sid and country and alias:
            sid = build_source_id(source_type, country, alias)
        if not sid:
            continue
        if sid not in selected_ids:
            selected_ids.append(sid)
            label_by_id[sid] = f"{country or 'N/A'} · {alias or 'Sin alias'}"

    return selected_ids, label_by_id


def render(settings: Settings) -> None:
    countries = supported_countries(settings)
    jira_delete_cfg: Dict[str, Any] = {"source_ids": [], "armed": False, "valid": True}
    helix_delete_cfg: Dict[str, Any] = {"source_ids": [], "armed": False, "valid": True}
    _inject_delete_zone_css()

    st.subheader("Configuración")

    t_jira, t_helix, t_kpis, t_prefs = st.tabs(
        ["🟦 Jira", "🟩 Helix", "📊 KPIs", "⭐ Preferencias"]
    )

    with t_jira:
        st.markdown("### Jira global")

        c1, c2 = st.columns(2)
        with c1:
            jira_base = st.text_input(
                "Jira Base URL (global)",
                value=settings.JIRA_BASE_URL,
                key="cfg_jira_base",
            )
        with c2:
            jira_browser = st.selectbox(
                "Navegador Jira (lectura cookie, global)",
                options=["chrome", "edge"],
                index=0 if settings.JIRA_BROWSER == "chrome" else 1,
                key="cfg_jira_browser",
            )

        st.markdown("### Fuentes Jira por país")
        st.caption("Alias y JQL son obligatorios.")
        jira_rows = _rows_from_jira_settings(settings, countries)
        jira_df = pd.DataFrame(
            jira_rows
            or [
                {
                    "__delete__": False,
                    "__source_id__": "",
                    "country": countries[0],
                    "alias": "",
                    "jql": "",
                }
            ]
        )
        jira_editor = st.data_editor(
            jira_df,
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            key="cfg_jira_sources_editor",
            column_order=["__delete__", "country", "alias", "jql"],
            column_config={
                "__delete__": st.column_config.CheckboxColumn("Eliminar"),
                "country": st.column_config.SelectboxColumn("country", options=countries),
                "alias": st.column_config.TextColumn("alias"),
                "jql": st.column_config.TextColumn("jql"),
            },
        )

        jira_delete_ids, jira_delete_labels = _selected_sources_from_editor(
            jira_editor, source_type="jira"
        )
        jira_delete_cfg = _render_source_delete_container(
            section_title="### 🧹 Eliminar fuente Jira",
            source_label="Jira",
            selected_source_ids=jira_delete_ids,
            selected_label_by_id=jira_delete_labels,
            key_prefix="cfg_jira",
        )

    with t_helix:
        st.markdown("### Helix defaults")
        h1, h2, h3, h4 = st.columns(4)
        with h1:
            helix_default_browser = st.selectbox(
                "Browser default",
                options=["chrome", "edge"],
                index=0 if _as_str(settings.HELIX_BROWSER) == "chrome" else 1,
                key="cfg_helix_browser_default",
            )
        with h2:
            helix_default_ssl_verify = st.selectbox(
                "SSL verify default",
                options=["true", "false"],
                index=(
                    0 if _boolish(getattr(settings, "HELIX_SSL_VERIFY", True), default=True) else 1
                ),
                key="cfg_helix_ssl_default",
            )
        with h3:
            helix_default_proxy = st.text_input(
                "Proxy default",
                value=_as_str(getattr(settings, "HELIX_PROXY", "")),
                key="cfg_helix_proxy_default",
            )
        with h4:
            helix_data_path = st.text_input(
                "Helix Data Path",
                value=_as_str(getattr(settings, "HELIX_DATA_PATH", "data/helix_dump.json")),
                key="cfg_helix_data_path",
            )

        st.markdown("### Fuentes Helix por país")
        helix_rows = _rows_from_helix_settings(settings, countries)
        helix_df = pd.DataFrame(
            helix_rows
            or [
                {
                    "__delete__": False,
                    "__source_id__": "",
                    "country": countries[0],
                    "alias": "",
                    "base_url": "",
                    "organization": "",
                    "browser": helix_default_browser,
                    "proxy": helix_default_proxy,
                    "ssl_verify": helix_default_ssl_verify,
                }
            ]
        )
        helix_editor = st.data_editor(
            helix_df,
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            key="cfg_helix_sources_editor",
            column_order=[
                "__delete__",
                "country",
                "alias",
                "base_url",
                "organization",
                "browser",
                "proxy",
                "ssl_verify",
            ],
            column_config={
                "__delete__": st.column_config.CheckboxColumn("Eliminar"),
                "country": st.column_config.SelectboxColumn("country", options=countries),
                "alias": st.column_config.TextColumn("alias"),
                "base_url": st.column_config.TextColumn("base_url"),
                "organization": st.column_config.TextColumn("organization"),
                "browser": st.column_config.SelectboxColumn("browser", options=["chrome", "edge"]),
                "proxy": st.column_config.TextColumn("proxy"),
                "ssl_verify": st.column_config.SelectboxColumn(
                    "ssl_verify", options=["true", "false"]
                ),
            },
        )

        helix_delete_ids, helix_delete_labels = _selected_sources_from_editor(
            helix_editor, source_type="helix"
        )
        helix_delete_cfg = _render_source_delete_container(
            section_title="### 🧹 Eliminar fuente Helix",
            source_label="Helix",
            selected_source_ids=helix_delete_ids,
            selected_label_by_id=helix_delete_labels,
            key_prefix="cfg_helix",
        )

    with t_kpis:
        st.markdown("### KPIs")

        k1, k2, k3 = st.columns(3)
        with k1:
            fort = st.number_input(
                "Días quincena (rodante)",
                min_value=1,
                value=int(settings.KPI_FORTNIGHT_DAYS),
                key="cfg_kpi_fortnight",
            )
        with k2:
            month = st.number_input(
                "Días mes (rodante)",
                min_value=1,
                value=int(settings.KPI_MONTH_DAYS),
                key="cfg_kpi_month",
            )
        with k3:
            open_age = st.text_input(
                "X días para '% abiertas > X' (coma)",
                value=settings.KPI_OPEN_AGE_X_DAYS,
                key="cfg_kpi_open_age",
            )

        age_buckets = st.text_input(
            "Buckets antigüedad (0-2,3-7,8-14,15-30,>30)",
            value=settings.KPI_AGE_BUCKETS,
            key="cfg_kpi_age_buckets",
        )

    with t_prefs:
        st.markdown("### ⭐ Favoritos (Tendencias)")
        st.caption("Define los 3 gráficos favoritos.")

        catalog = _trend_chart_catalog()
        all_ids = [cid for cid, _ in catalog]
        id_to_label = {cid: label for cid, label in catalog}

        stored = _parse_csv_ids(getattr(settings, "DASHBOARD_SUMMARY_CHARTS", ""), all_ids)
        if not stored:
            stored = _parse_csv_ids(getattr(settings, "TREND_SELECTED_CHARTS", ""), all_ids)

        fav1_default = stored[0] if len(stored) > 0 else all_ids[0]
        fav2_default = (
            stored[1] if len(stored) > 1 else (all_ids[1] if len(all_ids) > 1 else all_ids[0])
        )
        fav3_default = (
            stored[2] if len(stored) > 2 else (all_ids[2] if len(all_ids) > 2 else all_ids[0])
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            fav1 = st.selectbox(
                "Favorito 1",
                options=all_ids,
                index=all_ids.index(fav1_default),
                format_func=lambda x: id_to_label.get(x, x),
                key="cfg_trend_fav_1",
            )
        with c2:
            fav2 = st.selectbox(
                "Favorito 2",
                options=all_ids,
                index=all_ids.index(fav2_default),
                format_func=lambda x: id_to_label.get(x, x),
                key="cfg_trend_fav_2",
            )
        with c3:
            fav3 = st.selectbox(
                "Favorito 3",
                options=all_ids,
                index=all_ids.index(fav3_default),
                format_func=lambda x: id_to_label.get(x, x),
                key="cfg_trend_fav_3",
            )

    delete_forms_valid = bool(
        jira_delete_cfg.get("valid", True) and helix_delete_cfg.get("valid", True)
    )
    save_btn_help = None
    if not delete_forms_valid:
        save_btn_help = (
            "Completa la confirmación de eliminación (checkbox + texto ELIMINAR) "
            "o limpia esos campos para continuar."
        )

    if st.button(
        "💾 Guardar configuración",
        key="cfg_save_btn",
        disabled=not delete_forms_valid,
        help=save_btn_help,
    ):
        jira_clean, jira_errors = _normalize_jira_rows(jira_editor, countries)
        helix_clean, helix_errors = _normalize_helix_rows(helix_editor, countries)
        all_errors = jira_errors + helix_errors
        if all_errors:
            for err in all_errors:
                st.error(err)
            return

        summary_csv = ",".join([str(fav1), str(fav2), str(fav3)])
        update = dict(
            SUPPORTED_COUNTRIES=",".join(countries),
            JIRA_BASE_URL=jira_base.strip(),
            JIRA_BROWSER=jira_browser,
            JIRA_SOURCES_JSON=to_env_json(jira_clean),
            HELIX_SOURCES_JSON=to_env_json(helix_clean),
            HELIX_BROWSER=helix_default_browser,
            HELIX_PROXY=str(helix_default_proxy).strip(),
            HELIX_SSL_VERIFY=str(helix_default_ssl_verify).strip().lower(),
            HELIX_DATA_PATH=str(helix_data_path).strip(),
            KPI_FORTNIGHT_DAYS=str(fort),
            KPI_MONTH_DAYS=str(month),
            KPI_OPEN_AGE_X_DAYS=open_age.strip(),
            KPI_AGE_BUCKETS=age_buckets.strip(),
            DASHBOARD_SUMMARY_CHARTS=summary_csv,
            TREND_SELECTED_CHARTS=summary_csv,
        )

        new_settings = _safe_update_settings(settings, update)
        save_settings(new_settings)

        working_settings = new_settings
        any_deletion = False

        if bool(jira_delete_cfg.get("armed", False)):
            jira_delete_sids = [
                str(x).strip() for x in jira_delete_cfg.get("source_ids", []) if str(x).strip()
            ]
            jira_deleted = 0
            jira_purge_total = {
                "issues_removed": 0,
                "helix_items_removed": 0,
                "learning_scopes_removed": 0,
            }
            for delete_sid in jira_delete_sids:
                working_settings, deleted = remove_jira_source_from_settings(
                    working_settings, delete_sid
                )
                if not deleted:
                    st.warning(f"No se encontró la fuente Jira seleccionada: {delete_sid}.")
                    continue
                save_settings(working_settings)
                purge_stats = purge_source_cache(working_settings, delete_sid)
                jira_purge_total = _merge_purge_stats(jira_purge_total, purge_stats)
                jira_deleted += 1

            if jira_deleted > 0:
                st.success(f"Fuentes Jira eliminadas: {jira_deleted}. Cache saneado.")
                _render_purge_stats(jira_purge_total)
                any_deletion = True

        if bool(helix_delete_cfg.get("armed", False)):
            helix_delete_sids = [
                str(x).strip() for x in helix_delete_cfg.get("source_ids", []) if str(x).strip()
            ]
            helix_deleted = 0
            helix_purge_total = {
                "issues_removed": 0,
                "helix_items_removed": 0,
                "learning_scopes_removed": 0,
            }
            for delete_sid in helix_delete_sids:
                working_settings, deleted = remove_helix_source_from_settings(
                    working_settings, delete_sid
                )
                if not deleted:
                    st.warning(f"No se encontró la fuente Helix seleccionada: {delete_sid}.")
                    continue
                save_settings(working_settings)
                purge_stats = purge_source_cache(working_settings, delete_sid)
                helix_purge_total = _merge_purge_stats(helix_purge_total, purge_stats)
                helix_deleted += 1

            if helix_deleted > 0:
                st.success(f"Fuentes Helix eliminadas: {helix_deleted}. Cache saneado.")
                _render_purge_stats(helix_purge_total)
                any_deletion = True

        if any_deletion:
            st.success("Configuración y eliminación aplicadas.")
            st.rerun()
        else:
            st.success("Configuración guardada.")
