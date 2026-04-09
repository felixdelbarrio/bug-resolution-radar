"""Reusable topic-level expandable summaries for insights and reporting."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

import pandas as pd

from bug_resolution_radar.analytics.insights import classify_theme
from bug_resolution_radar.analytics.status_semantics import effective_finalized_at

_ROOT_CAUSE_RULES: tuple[tuple[str, tuple[tuple[str, int], ...]], ...] = (
    (
        "Autenticación y sesión",
        (
            (r"\blogin\b", 4),
            (r"\bacceso\b", 3),
            (r"\bpassword\b", 3),
            (r"\bcontrasena\b", 3),
            (r"\btoken\b", 2),
            (r"\botp\b", 3),
            (r"\bsesion\b", 3),
            (r"\bbiometr\w*\b", 4),
            (r"\bhuella\b", 3),
            (r"\bface\s+id\b", 4),
        ),
    ),
    (
        "Transferencias en tiempo real",
        (
            (r"\btransferencias?\s+en\s+tiempo\s+real\b", 9),
            (r"\btiempo\s+real\b", 4),
            (r"\bspei\b", 5),
            (r"\btransferencias?\b", 3),
            (r"\btraspasos?\b", 3),
            (r"\binterbanc\w*\b", 3),
        ),
    ),
    (
        "Conectividad / timeout",
        (
            (r"\btimeout\b", 5),
            (r"\blatencia\b", 4),
            (r"\blent[oa]s?\b", 3),
            (r"\bdemora\w*\b", 3),
            (r"\bno\s+responde\b", 5),
            (r"\bconexion\b", 3),
            (r"\bnetwork\b", 3),
            (r"\bgateway\b", 3),
            (r"\b(?:502|503|504)\b", 5),
        ),
    ),
    (
        "Visualización / UI",
        (
            (r"\bno\s+se\s+visualiza\b", 6),
            (r"\bno\s+se\s+muestra\b", 6),
            (r"\bpantalla\b", 3),
            (r"\bdashboard\b", 4),
            (r"\bui\b", 2),
            (r"\binterfaz\b", 4),
            (r"\bvista\b", 2),
            (r"\brender\w*\b", 3),
            (r"\ben\s+blanco\b", 4),
        ),
    ),
    (
        "Integración API / backend",
        (
            (r"\bapi\b", 4),
            (r"\bservicio\b", 3),
            (r"\bendpoint\b", 4),
            (r"\bmicroserv\w*\b", 4),
            (r"\bbackend\b", 4),
            (r"\bws\b", 2),
            (r"\bsoap\b", 4),
            (r"\brest\b", 3),
            (r"\bintegracion\b", 4),
            (r"\bsenda\b", 4),
            (r"\bbnc\b", 4),
            (r"\bsit\b", 4),
            (r"\bhost\b", 3),
        ),
    ),
    (
        "Validación de datos / reglas",
        (
            (r"\bno\s+permite\b", 5),
            (r"\binvalid\w*\b", 4),
            (r"\bvalidacion\b", 4),
            (r"\bformato\b", 3),
            (r"\bcampo\b", 2),
            (r"\bcaptura\b", 3),
            (r"\berror\s+de\s+datos\b", 5),
            (r"\bdatos?\b", 2),
            (r"\breglas?\b", 3),
        ),
    ),
    (
        "Notificaciones / mensajería",
        (
            (r"\bnotificacion\w*\b", 4),
            (r"\bpush\b", 4),
            (r"\bsms\b", 4),
            (r"\bcorreo\b", 3),
            (r"\bmensaje\w*\b", 3),
        ),
    ),
)
_ROOT_CAUSE_FALLBACK_LABEL = "Contexto funcional no especificado"

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
_OTHER_THEME_TOKENS: tuple[str, ...] = ("otros", "other")


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


def _compile_root_cause_rules() -> tuple[tuple[str, tuple[tuple[re.Pattern[str], int], ...]], ...]:
    compiled: list[tuple[str, tuple[tuple[re.Pattern[str], int], ...]]] = []
    for label, rules in _ROOT_CAUSE_RULES:
        compiled_rules: list[tuple[re.Pattern[str], int]] = []
        for pattern, weight in rules:
            compiled_rules.append((re.compile(str(pattern), flags=re.IGNORECASE), int(weight)))
        compiled.append((str(label), tuple(compiled_rules)))
    return tuple(compiled)


_COMPILED_ROOT_CAUSE_RULES = _compile_root_cause_rules()
_ROOT_CAUSE_ORDER = {label: idx for idx, (label, _) in enumerate(_COMPILED_ROOT_CAUSE_RULES)}


def _root_cause_scores(text: str) -> dict[str, int]:
    txt = str(text or "").strip()
    if not txt:
        return {}
    scores: dict[str, int] = {}
    for label, compiled_rules in _COMPILED_ROOT_CAUSE_RULES:
        score = 0
        for matcher, weight in compiled_rules:
            if matcher.search(txt):
                score += int(weight)
        if score > 0:
            scores[label] = score
    return scores


def _best_root_cause_label(scores: Mapping[str, int]) -> str:
    if not scores:
        return ""
    ranked = sorted(
        scores.items(),
        key=lambda item: (
            -int(item[1]),
            int(_ROOT_CAUSE_ORDER.get(str(item[0]), 10_000)),
            str(item[0]),
        ),
    )
    return str(ranked[0][0]).strip()


def _fallback_root_cause_label(summary: object, *, theme_hint: str | None = None) -> str:
    hint = str(theme_hint or "").strip()
    if hint:
        theme = hint
    else:
        theme = str(classify_theme(summary)).strip()
    theme_token = _normalize_text(theme)
    if theme and theme_token and theme_token not in _OTHER_THEME_TOKENS:
        return f"Fallo funcional en {theme}"
    return _ROOT_CAUSE_FALLBACK_LABEL


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


def infer_root_cause_label(summary: object, *, theme_hint: str | None = None) -> str:
    raw = _normalize_text(summary)
    if not raw:
        return _fallback_root_cause_label(summary, theme_hint=theme_hint)

    txt = re.sub(r"\[[^\]]*\]", " ", raw)
    txt = re.sub(r"\([^)]*\)", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    if not txt:
        return _fallback_root_cause_label(summary, theme_hint=theme_hint)

    scores = _root_cause_scores(txt)
    best = _best_root_cause_label(scores)
    if best:
        return best
    return _fallback_root_cause_label(summary, theme_hint=theme_hint)


def build_root_cause_map(
    summaries: Sequence[object],
    *,
    theme_hint_by_summary: Mapping[str, str] | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    hints = dict(theme_hint_by_summary or {})
    for raw_summary in list(summaries or []):
        summary_txt = str(raw_summary or "")
        if summary_txt in out:
            continue
        out[summary_txt] = infer_root_cause_label(
            summary_txt,
            theme_hint=hints.get(summary_txt, ""),
        )
    return out


def summarize_root_causes(
    summaries: Sequence[object],
    *,
    top_k: int = 3,
) -> tuple[RootCauseRank, ...]:
    summary_values = [str(summary or "") for summary in list(summaries or [])]
    label_map = build_root_cause_map(summary_values)
    labels = [str(label_map.get(summary, "") or "").strip() for summary in summary_values]
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
