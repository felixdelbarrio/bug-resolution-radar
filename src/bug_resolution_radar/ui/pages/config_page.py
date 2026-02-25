"""Configuration page to manage data sources and visualization preferences."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.analysis_window import (
    effective_analysis_lookback_months,
    max_available_backlog_months,
)
from bug_resolution_radar.config import (
    Settings,
    build_source_id,
    helix_sources,
    jira_sources,
    save_settings,
    supported_countries,
    to_env_json,
)
from bug_resolution_radar.services.source_maintenance import (
    cache_inventory,
    purge_source_cache,
    reset_cache_store,
)
from bug_resolution_radar.ui.cache import clear_signature_cache
from bug_resolution_radar.ui.common import load_issues_df


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
        ("resolution_hist", "Tiempo hasta estado final"),
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


def _is_reset_phrase_valid(value: Any) -> bool:
    return str(value or "").strip().upper() == "RESETEAR"


def _inject_delete_zone_css() -> None:
    st.markdown(
        """
        <style>
          [class*="st-key-cfg_jira_delete_shell"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-cfg_helix_delete_shell"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-cfg_cache_cache_reset_shell"] [data-testid="stVerticalBlockBorderWrapper"] {
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


def _inject_preferences_zone_css() -> None:
    st.markdown(
        """
        <style>
          [class*="st-key-cfg_tabs_shell"] div[data-baseweb="tab-list"] {
            gap: .35rem;
            padding: .28rem;
            border-radius: 14px;
            background:
              linear-gradient(180deg,
                color-mix(in srgb, var(--bbva-surface-elevated) 92%, #0E234C 8%),
                color-mix(in srgb, var(--bbva-surface) 97%, transparent)
              );
            border: 1px solid color-mix(in srgb, var(--bbva-border) 78%, #9BBBFF 22%);
            box-shadow: 0 8px 22px color-mix(in srgb, var(--bbva-text) 8%, transparent);
            width: fit-content;
          }
          [class*="st-key-cfg_tabs_shell"] button[role="tab"] {
            border-radius: 11px !important;
            border: 1px solid transparent !important;
            padding-inline: .95rem !important;
            transition: border-color .18s ease, box-shadow .18s ease, background-color .18s ease;
          }
          [class*="st-key-cfg_tabs_shell"] button[role="tab"][aria-selected="true"] {
            border-color: color-mix(in srgb, var(--bbva-primary) 52%, #8FB7FF 48%) !important;
            box-shadow: 0 0 0 1px color-mix(in srgb, var(--bbva-primary) 10%, transparent) inset;
            background:
              linear-gradient(180deg,
                color-mix(in srgb, var(--bbva-primary) 10%, var(--bbva-surface-elevated)),
                color-mix(in srgb, var(--bbva-primary) 4%, var(--bbva-surface))
              ) !important;
          }
          [class*="st-key-cfg_prefs_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid color-mix(in srgb, var(--bbva-border) 82%, #A2C1FF 18%) !important;
            border-radius: 16px !important;
            padding: .35rem .55rem .5rem !important;
            background:
              radial-gradient(900px 220px at 0% 0%, color-mix(in srgb, var(--bbva-primary) 8%, transparent), transparent 60%),
              linear-gradient(165deg, color-mix(in srgb, var(--bbva-surface) 97%, #0E234C 3%), var(--bbva-surface));
            box-shadow: 0 10px 26px color-mix(in srgb, var(--bbva-text) 6%, transparent) !important;
            margin-bottom: .7rem;
          }
          [class*="st-key-cfg_prefs_card_"] [data-testid="stMarkdownContainer"] h4 {
            letter-spacing: -.01em;
          }
          [class*="st-key-cfg_prefs_card_ppt"] input {
            font-weight: 600;
          }
          [class*="st-key-cfg_prefs_card_favs"] [data-testid="column"] {
            align-self: end;
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
            "La eliminación se ejecuta al pulsar Guardar en esta pestaña. "
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


def _rows_from_cache_inventory(settings: Settings) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in cache_inventory(settings):
        rows.append(
            {
                "__reset__": False,
                "__cache_id__": _as_str(row.get("cache_id")),
                "cache": _as_str(row.get("label")),
                "registros": int(row.get("records", 0) or 0),
                "ruta": _as_str(row.get("path")),
            }
        )
    return rows


def _selected_caches_from_editor(df: pd.DataFrame) -> Tuple[List[str], Dict[str, str]]:
    selected_ids: List[str] = []
    label_by_id: Dict[str, str] = {}

    for row in df.to_dict(orient="records"):
        if not _boolish(row.get("__reset__"), default=False):
            continue
        cache_id = _as_str(row.get("__cache_id__"))
        label = _as_str(row.get("cache")) or cache_id
        if not cache_id:
            continue
        if cache_id not in selected_ids:
            selected_ids.append(cache_id)
            label_by_id[cache_id] = label
    return selected_ids, label_by_id


def _render_cache_reset_container(
    *,
    selected_cache_ids: List[str],
    selected_label_by_id: Dict[str, str],
    key_prefix: str,
) -> Dict[str, Any]:
    st.markdown("### ♻️ Resetear caché")

    with st.container(border=True, key=f"{key_prefix}_cache_reset_shell"):
        st.markdown("#### Zona segura de reseteo")
        st.caption(
            "La operación es inmediata y vacía el contenido del cache seleccionado "
            "(deja 0 registros). No requiere Guardar configuración."
        )

        has_selection = bool(selected_cache_ids)
        if has_selection:
            plural = "s" if len(selected_cache_ids) != 1 else ""
            st.markdown(
                f'<div class="cfg-delete-counter"><strong>{len(selected_cache_ids)}</strong> '
                f"cache{plural} seleccionado{plural}.</div>",
                unsafe_allow_html=True,
            )
            _render_selected_source_chips(selected_cache_ids, selected_label_by_id)
        else:
            st.markdown(
                '<div class="cfg-delete-ghost">Marca en la tabla los caches que quieras resetear. '
                "Aquí aparecerán como chips.</div>",
                unsafe_allow_html=True,
            )

        confirm = st.checkbox(
            "Confirmo que quiero resetear los caches seleccionados.",
            key=f"{key_prefix}_cache_reset_confirm",
        )
        phrase = st.text_input(
            "Escribe RESETEAR para confirmar",
            value="",
            key=f"{key_prefix}_cache_reset_phrase",
            help="Confirmación reforzada para evitar resets accidentales.",
        )
        phrase_ok = _is_reset_phrase_valid(phrase)
        has_partial_input = bool(has_selection or confirm or str(phrase).strip())
        armed = bool(has_selection and confirm and phrase_ok)
        valid = bool((not has_partial_input) or armed)

        if has_partial_input and not has_selection:
            st.warning("Selecciona al menos un cache para resetear.")
        elif has_partial_input and not armed:
            st.warning(
                "Para aplicar el reseteo debes seleccionar caches, "
                "marcar confirmación y escribir RESETEAR."
            )
        elif armed:
            st.success(
                f"Reseteo preparado ({len(selected_cache_ids)}). "
                "Pulsa el botón para vaciar los registros."
            )

        return {"cache_ids": selected_cache_ids, "armed": armed, "valid": valid}


def _render_cache_reset_results(results: List[Dict[str, Any]]) -> None:
    if not results:
        return
    for row in results:
        label = str(row.get("label") or row.get("cache_id") or "cache")
        before = int(row.get("before", 0) or 0)
        after = int(row.get("after", 0) or 0)
        reset = int(row.get("reset", 0) or 0)
        st.info(f"{label}: {before} -> {after} registros (reseteados {reset}).")


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
                "service_origin_buug": _as_str(src.get("service_origin_buug")),
                "service_origin_n1": _as_str(src.get("service_origin_n1")),
                "service_origin_n2": _as_str(src.get("service_origin_n2")),
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
        service_origin_buug = _as_str(row.get("service_origin_buug"))
        service_origin_n1 = _as_str(row.get("service_origin_n1"))
        service_origin_n2 = _as_str(row.get("service_origin_n2"))
        browser = _as_str(row.get("browser")) or "chrome"
        proxy = _as_str(row.get("proxy"))
        ssl_verify = _as_str(row.get("ssl_verify")) or "true"

        if not any(
            [
                country,
                alias,
                base_url,
                organization,
                proxy,
                service_origin_buug,
                service_origin_n1,
                service_origin_n2,
            ]
        ):
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
        payload = {
            "country": country,
            "alias": alias,
            "base_url": base_url,
            "organization": organization,
            "browser": browser,
            "proxy": proxy,
            "ssl_verify": ssl_verify,
        }
        if service_origin_buug:
            payload["service_origin_buug"] = service_origin_buug
        if service_origin_n1:
            payload["service_origin_n1"] = service_origin_n1
        if service_origin_n2:
            payload["service_origin_n2"] = service_origin_n2
        out.append(payload)

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


def _clear_delete_confirmation_widget_state() -> None:
    for key in (
        "cfg_jira_delete_confirm",
        "cfg_jira_delete_phrase",
        "cfg_helix_delete_confirm",
        "cfg_helix_delete_phrase",
    ):
        st.session_state.pop(key, None)


def _clear_jira_delete_widget_state() -> None:
    for key in (
        "cfg_jira_delete_confirm",
        "cfg_jira_delete_phrase",
        "cfg_jira_sources_editor",
    ):
        st.session_state.pop(key, None)


def _clear_helix_delete_widget_state() -> None:
    for key in (
        "cfg_helix_delete_confirm",
        "cfg_helix_delete_phrase",
        "cfg_helix_sources_editor",
    ):
        st.session_state.pop(key, None)


def _clear_cache_reset_widget_state() -> None:
    for key in (
        "cfg_cache_reset_editor",
        "cfg_cache_cache_reset_confirm",
        "cfg_cache_cache_reset_phrase",
    ):
        st.session_state.pop(key, None)


def _clear_config_delete_widget_state() -> None:
    _clear_delete_confirmation_widget_state()
    _clear_jira_delete_widget_state()
    _clear_helix_delete_widget_state()


def _apply_workspace_scope(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    selected_country = str(st.session_state.get("workspace_country") or "").strip()
    selected_source_id = str(st.session_state.get("workspace_source_id") or "").strip()
    if not selected_country and not selected_source_id:
        return df.copy(deep=False)

    mask = pd.Series(True, index=df.index)
    if selected_country and "country" in df.columns:
        mask &= df["country"].fillna("").astype(str).eq(selected_country)
    if selected_source_id and "source_id" in df.columns:
        mask &= df["source_id"].fillna("").astype(str).eq(selected_source_id)
    return df.loc[mask].copy(deep=False)


def _analysis_window_defaults(settings: Settings) -> Tuple[int, int]:
    try:
        df_all = load_issues_df(settings.DATA_PATH)
    except Exception:
        return 1, 1

    if df_all.empty:
        return 1, 1

    scoped_df = _apply_workspace_scope(df_all)
    base_df = scoped_df if not scoped_df.empty else df_all
    available_months = int(max_available_backlog_months(base_df))
    current_months = int(effective_analysis_lookback_months(settings, df=base_df))
    return max(1, available_months), max(1, min(current_months, available_months))


def _analysis_month_steps(max_months: int) -> List[int]:
    target = max(1, int(max_months))
    base_steps = [1, 2, 3, 4, 6, 9, 12, 18, 24, 36, 48, 60]
    options = sorted({m for m in base_steps if m <= target} | {target})
    return options or [1]


def _nearest_option(value: int, *, options: List[int]) -> int:
    if not options:
        return max(1, int(value))
    tgt = max(1, int(value))
    return min(options, key=lambda opt: abs(int(opt) - tgt))


def render(settings: Settings) -> None:
    flash_success = str(st.session_state.pop("__cfg_flash_success", "") or "").strip()
    if flash_success:
        st.success(flash_success)

    countries = supported_countries(settings)
    jira_delete_cfg: Dict[str, Any] = {"source_ids": [], "armed": False, "valid": True}
    helix_delete_cfg: Dict[str, Any] = {"source_ids": [], "armed": False, "valid": True}
    analysis_max_months = 1
    analysis_selected_months = 1
    _inject_delete_zone_css()
    _inject_preferences_zone_css()

    st.subheader("Configuración")

    # Avoid emoji icons in tab labels: some environments render them as empty squares.
    with st.container(key="cfg_tabs_shell"):
        t_prefs, t_jira, t_helix, t_caches = st.tabs(["Preferencias", "Jira", "Helix", "Caches"])

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

        jira_save_help = None
        if not bool(jira_delete_cfg.get("valid", True)):
            jira_save_help = (
                "Completa la confirmación de eliminación (checkbox + texto ELIMINAR) "
                "o limpia esos campos para continuar."
            )
        if st.button(
            "💾 Guardar configuración",
            key="cfg_save_jira_btn",
            disabled=not bool(jira_delete_cfg.get("valid", True)),
            help=jira_save_help,
        ):
            jira_clean, jira_errors = _normalize_jira_rows(jira_editor, countries)
            if jira_errors:
                for err in jira_errors:
                    st.error(err)
                return

            new_settings = _safe_update_settings(
                settings,
                {
                    "JIRA_BASE_URL": str(jira_base).strip(),
                    "JIRA_BROWSER": str(jira_browser).strip(),
                    "JIRA_SOURCES_JSON": to_env_json(jira_clean),
                },
            )
            save_settings(new_settings)

            any_deletion = False
            if bool(jira_delete_cfg.get("armed", False)):
                jira_delete_sids = [
                    str(x).strip() for x in jira_delete_cfg.get("source_ids", []) if str(x).strip()
                ]
                if jira_delete_sids:
                    any_deletion = True
                    jira_purge_total = {
                        "issues_removed": 0,
                        "helix_items_removed": 0,
                        "learning_scopes_removed": 0,
                    }
                    for delete_sid in jira_delete_sids:
                        purge_stats = purge_source_cache(new_settings, delete_sid)
                        jira_purge_total = _merge_purge_stats(jira_purge_total, purge_stats)
                    st.success(f"Fuentes Jira eliminadas: {len(jira_delete_sids)}. Cache saneado.")
                    _render_purge_stats(jira_purge_total)

            if any_deletion:
                _clear_jira_delete_widget_state()
                st.session_state["__cfg_flash_success"] = (
                    "Configuración Jira y eliminación aplicadas."
                )
            else:
                for key in ("cfg_jira_delete_confirm", "cfg_jira_delete_phrase"):
                    st.session_state.pop(key, None)
                st.session_state["__cfg_flash_success"] = "Configuración Jira guardada."
            st.rerun()

    with t_helix:
        st.markdown("### Helix defaults")
        query_mode_current = _as_str(getattr(settings, "HELIX_QUERY_MODE", "arsql")).lower()
        if query_mode_current not in {"arsql", "person_workitems"}:
            query_mode_current = "arsql"
        helix_query_mode_labels = {
            "arsql": "ARSQL (dashboards/report/arsqlquery)",
            "person_workitems": "Helix API (/rest/v2/person/workitems/get)",
        }

        h1, h2, h3 = st.columns(3)
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
            helix_query_mode = st.selectbox(
                "Modo de ingesta",
                options=["arsql", "person_workitems"],
                index=0 if query_mode_current == "arsql" else 1,
                format_func=lambda x: helix_query_mode_labels.get(x, x),
                key="cfg_helix_query_mode",
            )

        h4, h5 = st.columns(2)
        with h4:
            helix_default_proxy = st.text_input(
                "Proxy default",
                value=_as_str(getattr(settings, "HELIX_PROXY", "")),
                key="cfg_helix_proxy_default",
            )
        with h5:
            helix_data_path = st.text_input(
                "Helix Data Path",
                value=_as_str(getattr(settings, "HELIX_DATA_PATH", "data/helix_dump.json")),
                key="cfg_helix_data_path",
            )
        helix_dashboard_url = st.text_input(
            "Helix Dashboard URL (base apertura ticket)",
            value=_as_str(
                getattr(
                    settings,
                    "HELIX_DASHBOARD_URL",
                    "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
                )
            ),
            key="cfg_helix_dashboard_url",
        )
        if helix_query_mode == "arsql":
            st.caption("Modo activo: ARSQL (por defecto).")
        else:
            st.caption("Modo activo: endpoint Helix clásico person/workitems/get.")

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
                    "service_origin_buug": "BBVA México",
                    "service_origin_n1": "ENTERPRISE WEB",
                    "service_origin_n2": "",
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
                "service_origin_buug",
                "service_origin_n1",
                "service_origin_n2",
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
                "service_origin_buug": st.column_config.TextColumn("Servicio Origen BU/UG"),
                "service_origin_n1": st.column_config.TextColumn("Servicio Origen N1 (CSV)"),
                "service_origin_n2": st.column_config.TextColumn("Servicio Origen N2 (CSV)"),
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

        helix_save_help = None
        if not bool(helix_delete_cfg.get("valid", True)):
            helix_save_help = (
                "Completa la confirmación de eliminación (checkbox + texto ELIMINAR) "
                "o limpia esos campos para continuar."
            )
        if st.button(
            "💾 Guardar configuración",
            key="cfg_save_helix_btn",
            disabled=not bool(helix_delete_cfg.get("valid", True)),
            help=helix_save_help,
        ):
            helix_clean, helix_errors = _normalize_helix_rows(helix_editor, countries)
            if helix_errors:
                for err in helix_errors:
                    st.error(err)
                return

            new_settings = _safe_update_settings(
                settings,
                {
                    "HELIX_SOURCES_JSON": to_env_json(helix_clean),
                    "HELIX_BROWSER": str(helix_default_browser).strip(),
                    "HELIX_PROXY": str(helix_default_proxy).strip(),
                    "HELIX_SSL_VERIFY": str(helix_default_ssl_verify).strip().lower(),
                    "HELIX_QUERY_MODE": str(helix_query_mode).strip().lower(),
                    "HELIX_DATA_PATH": str(helix_data_path).strip(),
                    "HELIX_DASHBOARD_URL": str(helix_dashboard_url).strip(),
                },
            )
            save_settings(new_settings)

            any_deletion = False
            if bool(helix_delete_cfg.get("armed", False)):
                helix_delete_sids = [
                    str(x).strip() for x in helix_delete_cfg.get("source_ids", []) if str(x).strip()
                ]
                if helix_delete_sids:
                    any_deletion = True
                    helix_purge_total = {
                        "issues_removed": 0,
                        "helix_items_removed": 0,
                        "learning_scopes_removed": 0,
                    }
                    for delete_sid in helix_delete_sids:
                        purge_stats = purge_source_cache(new_settings, delete_sid)
                        helix_purge_total = _merge_purge_stats(helix_purge_total, purge_stats)
                    st.success(
                        f"Fuentes Helix eliminadas: {len(helix_delete_sids)}. Cache saneado."
                    )
                    _render_purge_stats(helix_purge_total)

            if any_deletion:
                _clear_helix_delete_widget_state()
                st.session_state["__cfg_flash_success"] = (
                    "Configuración Helix y eliminación aplicadas."
                )
            else:
                for key in ("cfg_helix_delete_confirm", "cfg_helix_delete_phrase"):
                    st.session_state.pop(key, None)
                st.session_state["__cfg_flash_success"] = "Configuración Helix guardada."
            st.rerun()

    with t_prefs:
        with st.container(key="cfg_prefs_shell"):
            st.markdown("### Favoritos (Tendencias)")
            stored_theme_pref = str(getattr(settings, "THEME", "auto") or "auto").strip().lower()
            if stored_theme_pref in {"dark", "light"}:
                theme_default = stored_theme_pref
            else:
                theme_default = (
                    "dark" if bool(st.session_state.get("workspace_dark_mode", False)) else "light"
                )

            with st.container(key="cfg_prefs_card_workspace"):
                st.markdown("#### Ambiente de trabajo")
                theme_mode = st.radio(
                    "Modo visual",
                    options=["light", "dark"],
                    index=0 if theme_default == "light" else 1,
                    format_func=lambda v: "Claro" if v == "light" else "Oscuro",
                    horizontal=True,
                    key="cfg_workspace_theme_mode",
                )
                st.caption("Se guarda en el .env como preferencia del usuario.")

            with st.container(key="cfg_prefs_card_analysis"):
                st.markdown("#### Profundidad del análisis")
                analysis_max_months, analysis_selected_months = _analysis_window_defaults(settings)
                month_options = _analysis_month_steps(analysis_max_months)
                if len(month_options) <= 1:
                    only_month = int(month_options[0]) if month_options else 1
                    analysis_selected_months = only_month
                    st.session_state["cfg_analysis_depth_months"] = only_month
                    st.selectbox(
                        "Meses analizados en backlog",
                        options=[only_month],
                        index=0,
                        key="cfg_analysis_depth_months_single",
                        disabled=True,
                        format_func=lambda m: (
                            f"{int(m)} mes" if int(m) == 1 else f"{int(m)} meses"
                        ),
                        help=(
                            "Se habilita automáticamente cuando exista histórico suficiente "
                            "en la caché de incidencias."
                        ),
                    )
                else:
                    st.session_state.pop("cfg_analysis_depth_months_single", None)
                    analysis_selected_months = st.select_slider(
                        "Meses analizados en backlog",
                        options=month_options,
                        value=_nearest_option(analysis_selected_months, options=month_options),
                        key="cfg_analysis_depth_months",
                        format_func=lambda m: f"{int(m)} mes" if int(m) == 1 else f"{int(m)} meses",
                        help=(
                            "Filtro global oculto aplicado de forma transversal en dashboard, insights e informe PPT. "
                            "Si lo dejas al máximo, se usa toda la profundidad disponible."
                        ),
                    )
                if int(analysis_selected_months) >= int(analysis_max_months):
                    st.caption("Estado: profundidad máxima disponible (modo automático).")
                else:
                    st.caption(
                        f"Estado: últimos {int(analysis_selected_months)} "
                        f"{'mes' if int(analysis_selected_months) == 1 else 'meses'}."
                    )

            with st.container(key="cfg_prefs_card_ppt"):
                st.markdown("#### Descargas del informe PPT")
                st.markdown("**Carpeta de guardado**")
                report_ppt_download_dir_default = str(
                    getattr(settings, "REPORT_PPT_DOWNLOAD_DIR", "") or ""
                ).strip() or str((Path.home() / "Downloads").expanduser())
                report_ppt_download_dir = st.text_input(
                    "Carpeta de guardado del informe PPT",
                    value=report_ppt_download_dir_default,
                    key="cfg_report_ppt_download_dir",
                    label_visibility="collapsed",
                    placeholder=str((Path.home() / "Downloads").expanduser()),
                )

            with st.container(key="cfg_prefs_card_favs"):
                st.markdown("**Define los 3 gráficos favoritos**")

                catalog = _trend_chart_catalog()
                all_ids = [cid for cid, _ in catalog]
                id_to_label = {cid: label for cid, label in catalog}

                stored = _parse_csv_ids(getattr(settings, "DASHBOARD_SUMMARY_CHARTS", ""), all_ids)
                if not stored:
                    stored = _parse_csv_ids(getattr(settings, "TREND_SELECTED_CHARTS", ""), all_ids)

                fav1_default = stored[0] if len(stored) > 0 else all_ids[0]
                fav2_default = (
                    stored[1]
                    if len(stored) > 1
                    else (all_ids[1] if len(all_ids) > 1 else all_ids[0])
                )
                fav3_default = (
                    stored[2]
                    if len(stored) > 2
                    else (all_ids[2] if len(all_ids) > 2 else all_ids[0])
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

            if st.button("💾 Guardar configuración", key="cfg_save_prefs_btn"):
                summary_csv = ",".join([str(fav1), str(fav2), str(fav3)])
                analysis_lookback_months_to_store = (
                    0
                    if int(analysis_selected_months) >= int(analysis_max_months)
                    else int(analysis_selected_months)
                )
                new_settings = _safe_update_settings(
                    settings,
                    {
                        "THEME": str(theme_mode).strip().lower(),
                        "DASHBOARD_SUMMARY_CHARTS": summary_csv,
                        "TREND_SELECTED_CHARTS": summary_csv,
                        "REPORT_PPT_DOWNLOAD_DIR": str(report_ppt_download_dir).strip(),
                        "ANALYSIS_LOOKBACK_MONTHS": analysis_lookback_months_to_store,
                        "ANALYSIS_LOOKBACK_DAYS": 0,
                    },
                )
                save_settings(new_settings)
                target_dark_mode = str(theme_mode).strip().lower() == "dark"
                theme_mode_changed = (
                    bool(st.session_state.get("workspace_dark_mode", False)) != target_dark_mode
                )
                if theme_mode_changed:
                    st.session_state["workspace_dark_mode"] = target_dark_mode
                    st.session_state["__cfg_flash_success"] = (
                        "Preferencias guardadas. Modo visual actualizado."
                    )
                else:
                    st.session_state["__cfg_flash_success"] = "Preferencias guardadas."
                st.rerun()

    with t_caches:
        st.markdown("### Caches")
        st.caption("Resetea caches persistentes de la aplicación sin afectar la configuración.")

        cache_rows = _rows_from_cache_inventory(settings)
        cache_df = pd.DataFrame(
            cache_rows
            or [
                {
                    "__reset__": False,
                    "__cache_id__": "",
                    "cache": "Sin caches configurados",
                    "registros": 0,
                    "ruta": "",
                }
            ]
        )
        cache_editor = st.data_editor(
            cache_df,
            hide_index=True,
            num_rows="fixed",
            width="stretch",
            key="cfg_cache_reset_editor",
            column_order=["__reset__", "cache", "registros", "ruta"],
            column_config={
                "__reset__": st.column_config.CheckboxColumn("Resetear"),
                "cache": st.column_config.TextColumn("Cache"),
                "registros": st.column_config.NumberColumn("Registros", format="%d"),
                "ruta": st.column_config.TextColumn("Ruta"),
            },
            disabled=["cache", "registros", "ruta"],
        )
        cache_reset_ids, cache_reset_labels = _selected_caches_from_editor(cache_editor)
        cache_reset_cfg = _render_cache_reset_container(
            selected_cache_ids=cache_reset_ids,
            selected_label_by_id=cache_reset_labels,
            key_prefix="cfg_cache",
        )
        cache_reset_disabled = not bool(cache_reset_cfg.get("armed", False))
        if st.button(
            "♻️ Resetear caches seleccionados",
            key="cfg_cache_reset_btn",
            disabled=cache_reset_disabled,
            help=(
                "Selecciona caches, marca confirmación y escribe RESETEAR."
                if cache_reset_disabled
                else None
            ),
        ):
            selected_cache_ids = [
                str(x).strip() for x in cache_reset_cfg.get("cache_ids", []) if str(x).strip()
            ]
            results: List[Dict[str, Any]] = []
            for cache_id in selected_cache_ids:
                results.append(reset_cache_store(settings, cache_id))
            try:
                st.cache_data.clear()
            except Exception:
                pass
            clear_signature_cache()
            _clear_cache_reset_widget_state()
            st.session_state["__cfg_cache_reset_results"] = results
            total_reset = sum(int(row.get("reset", 0) or 0) for row in results)
            st.session_state["__cfg_flash_success"] = (
                f"Reset de cache completado ({len(results)} seleccionado(s), {total_reset} registros vaciados)."
            )
            st.rerun()

        cache_reset_results = st.session_state.pop("__cfg_cache_reset_results", None)
        if isinstance(cache_reset_results, list) and cache_reset_results:
            _render_cache_reset_results(cache_reset_results)
