"""Reusable topic-level expandable summaries for insights and reporting."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal, Sequence

import pandas as pd

from bug_resolution_radar.analytics.insights import classify_theme
from bug_resolution_radar.analytics.status_semantics import effective_finalized_at

_ROOT_CAUSE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Autenticación y sesión",
        (
            "login",
            "acceso",
            "password",
            "contrasena",
            "contraseña",
            "token",
            "otp",
            "sesion",
            "sesión",
            "biometr",
            "huella",
            "face id",
        ),
    ),
    (
        "Conectividad / timeout",
        (
            "timeout",
            "latencia",
            "lento",
            "demora",
            "no responde",
            "conexion",
            "conexión",
            "network",
            "gateway",
            "502",
            "503",
            "504",
        ),
    ),
    (
        "Visualización / UI",
        (
            "no se visualiza",
            "no se muestra",
            "pantalla",
            "dashboard",
            "ui",
            "interfaz",
            "vista",
            "render",
            "blanco",
        ),
    ),
    (
        "Integración API / backend",
        (
            "api",
            "servicio",
            "endpoint",
            "microserv",
            "backend",
            "ws",
            "soap",
            "rest",
            "integracion",
            "integración",
        ),
    ),
    (
        "Validación de datos / reglas",
        (
            "no permite",
            "invalido",
            "inválido",
            "validacion",
            "validación",
            "formato",
            "campo",
            "captura",
            "error de datos",
            "dato",
        ),
    ),
    (
        "Notificaciones / mensajería",
        (
            "notificacion",
            "notificación",
            "push",
            "sms",
            "correo",
            "mensaje",
        ),
    ),
)

_ROOT_CAUSE_STOPWORDS: set[str] = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "en",
    "con",
    "por",
    "para",
    "sin",
    "and",
    "the",
    "una",
    "un",
    "que",
    "se",
    "no",
}


@dataclass(frozen=True)
class RootCauseRank:
    label: str
    count: int


@dataclass(frozen=True)
class TopicFlowSummary:
    created_count: int
    resolved_count: int
    pct_delta: float
    direction: Literal["improving", "worsening", "stable"]
    window_days: int


@dataclass(frozen=True)
class TopicExpandableSummary:
    flow: TopicFlowSummary
    root_causes: tuple[RootCauseRank, ...]


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _normalize_text(value: object) -> str:
    txt = str(value or "").strip().lower()
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = txt.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", txt).strip()


def _to_dt_naive(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return out.dt.tz_convert(None)
    except Exception:
        try:
            return out.dt.tz_localize(None)
        except Exception:
            return out


def ensure_theme_column(
    df: pd.DataFrame,
    *,
    theme_col: str = "__theme",
    summary_col: str = "summary",
) -> pd.DataFrame:
    safe = _safe_df(df)
    if safe.empty or summary_col not in safe.columns:
        return safe
    work = safe.copy(deep=False)
    if theme_col in work.columns:
        return work
    summaries = work[summary_col].fillna("").astype(str)
    unique_summaries = pd.unique(summaries.to_numpy(copy=False)).tolist()
    theme_map = {txt: classify_theme(txt) for txt in unique_summaries}
    work[theme_col] = summaries.map(theme_map).to_numpy(copy=False)
    return work


def infer_root_cause_label(summary: object) -> str:
    raw = _normalize_text(summary)
    if not raw:
        return "Sin detalle suficiente"

    txt = re.sub(r"\[[^\]]*\]", " ", raw)
    txt = re.sub(r"\([^)]*\)", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    if not txt:
        return "Sin detalle suficiente"

    for label, keywords in _ROOT_CAUSE_RULES:
        if any(str(token) in txt for token in keywords):
            return label

    tokens = [
        t for t in re.findall(r"[a-z0-9]+", txt) if len(t) >= 4 and t not in _ROOT_CAUSE_STOPWORDS
    ]
    if not tokens:
        return "Sin detalle suficiente"
    return f"Patrón: {' '.join(tokens[:2])}"


def summarize_root_causes(
    summaries: Sequence[object],
    *,
    top_k: int = 3,
) -> tuple[RootCauseRank, ...]:
    labels = [infer_root_cause_label(summary) for summary in list(summaries or [])]
    labels = [label for label in labels if str(label).strip()]
    if not labels:
        return ()

    counts = Counter(labels)
    ranked = sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    return tuple(
        RootCauseRank(label=str(label), count=int(count))
        for label, count in ranked[: max(int(top_k or 3), 1)]
    )


def _build_topic_flow_summary(
    *,
    created_count: int,
    resolved_count: int,
    window_days: int,
) -> TopicFlowSummary:
    created_i = max(int(created_count or 0), 0)
    resolved_i = max(int(resolved_count or 0), 0)

    if resolved_i > created_i:
        pct = ((resolved_i - created_i) / max(resolved_i, 1)) * 100.0
        direction: Literal["improving", "worsening", "stable"] = "improving"
    elif created_i > resolved_i:
        pct = ((created_i - resolved_i) / max(created_i, 1)) * 100.0
        direction = "worsening"
    else:
        pct = 0.0
        direction = "stable"

    return TopicFlowSummary(
        created_count=created_i,
        resolved_count=resolved_i,
        pct_delta=float(pct),
        direction=direction,
        window_days=max(int(window_days or 30), 1),
    )


def build_topic_expandable_summaries(
    *,
    history_df: pd.DataFrame,
    open_df: pd.DataFrame,
    theme_col: str = "__theme",
    created_col: str = "created",
    resolved_col: str = "resolved",
    status_col: str = "status",
    top_root_causes: int = 3,
    flow_window_days: int = 30,
) -> dict[str, TopicExpandableSummary]:
    hist = ensure_theme_column(history_df, theme_col=theme_col)
    open_now = ensure_theme_column(open_df, theme_col=theme_col)
    out: dict[str, TopicExpandableSummary] = {}
    if hist.empty and open_now.empty:
        return out

    window_days = max(int(flow_window_days or 30), 1)
    flow_by_topic: dict[str, TopicFlowSummary] = {}
    if not hist.empty and theme_col in hist.columns:
        created_dt = (
            _to_dt_naive(hist[created_col])
            if created_col in hist.columns
            else pd.Series(pd.NaT, index=hist.index)
        )
        finalized_dt = effective_finalized_at(
            hist,
            created_col=created_col,
            resolved_col=resolved_col,
            status_col=status_col,
        )

        reference_candidates: list[pd.Timestamp] = []
        if isinstance(created_dt, pd.Series) and created_dt.notna().any():
            reference_candidates.append(pd.Timestamp(created_dt.max()))
        if isinstance(finalized_dt, pd.Series) and finalized_dt.notna().any():
            reference_candidates.append(pd.Timestamp(finalized_dt.max()))
        reference_day = (
            max(reference_candidates).normalize()
            if reference_candidates
            else pd.Timestamp.utcnow().tz_localize(None).normalize()
        )
        window_start = reference_day - pd.Timedelta(days=window_days)
        created_recent = created_dt.notna() & (created_dt >= window_start)
        resolved_recent = finalized_dt.notna() & (finalized_dt >= window_start)

        flow_tbl = (
            pd.DataFrame(
                {
                    "tema": hist[theme_col].fillna("").astype(str),
                    "__created_recent": created_recent.astype(int),
                    "__resolved_recent": resolved_recent.astype(int),
                }
            )
            .groupby("tema", dropna=False, as_index=False)
            .agg(
                created_recent=("__created_recent", "sum"),
                resolved_recent=("__resolved_recent", "sum"),
            )
        )
        flow_tbl = flow_tbl[flow_tbl["tema"].astype(str).str.strip() != ""]
        for _, row in flow_tbl.iterrows():
            topic = str(row.get("tema", "") or "").strip()
            if not topic:
                continue
            flow_by_topic[topic] = _build_topic_flow_summary(
                created_count=int(row.get("created_recent", 0) or 0),
                resolved_count=int(row.get("resolved_recent", 0) or 0),
                window_days=window_days,
            )

    roots_by_topic: dict[str, tuple[RootCauseRank, ...]] = {}
    if not open_now.empty and theme_col in open_now.columns and "summary" in open_now.columns:
        for topic, sub in open_now.groupby(theme_col, dropna=False):
            topic_name = str(topic or "").strip()
            if not topic_name:
                continue
            roots_by_topic[topic_name] = summarize_root_causes(
                sub["summary"].fillna("").astype(str).tolist(),
                top_k=top_root_causes,
            )

    all_topics = set(flow_by_topic.keys()) | set(roots_by_topic.keys())
    for topic in all_topics:
        out[topic] = TopicExpandableSummary(
            flow=flow_by_topic.get(
                topic,
                _build_topic_flow_summary(
                    created_count=0, resolved_count=0, window_days=window_days
                ),
            ),
            root_causes=roots_by_topic.get(topic, ()),
        )
    return out
