"""Configuration page to manage data sources and visualization preferences."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import (
    Settings,
    helix_sources,
    jira_sources,
    save_settings,
    supported_countries,
    to_env_json,
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
        ("open_priority_pie", "Abiertas por Priority (pie)"),
        ("open_status_bar", "Abiertas por Estado (bar)"),
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


def _rows_from_jira_settings(settings: Settings, countries: List[str]) -> List[Dict[str, str]]:
    rows = []
    for src in jira_sources(settings):
        country = _as_str(src.get("country"))
        if country not in countries:
            continue
        rows.append(
            {
                "country": country,
                "alias": _as_str(src.get("alias")),
                "jql": _as_str(src.get("jql")),
            }
        )
    return rows


def _rows_from_helix_settings(settings: Settings, countries: List[str]) -> List[Dict[str, str]]:
    rows = []
    for src in helix_sources(settings):
        country = _as_str(src.get("country"))
        if country not in countries:
            continue
        rows.append(
            {
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


def render(settings: Settings) -> None:
    countries = supported_countries(settings)

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
        jira_df = pd.DataFrame(jira_rows or [{"country": countries[0], "alias": "", "jql": ""}])
        jira_editor = st.data_editor(
            jira_df,
            hide_index=True,
            num_rows="dynamic",
            use_container_width=True,
            key="cfg_jira_sources_editor",
            column_config={
                "country": st.column_config.SelectboxColumn("country", options=countries),
                "alias": st.column_config.TextColumn("alias"),
                "jql": st.column_config.TextColumn("jql"),
            },
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
            use_container_width=True,
            key="cfg_helix_sources_editor",
            column_config={
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

    st.markdown("---")

    if st.button("💾 Guardar configuración", key="cfg_save_btn"):
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
        st.success("Configuración guardada.")
