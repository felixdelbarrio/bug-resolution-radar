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
_FALLBACK_THEME_PREFIX = "Fallo funcional en "
_SEMANTIC_HINT_TOKENS: tuple[str, ...] = (
    "transfer",
    "traspas",
    "spei",
    "api",
    "backend",
    "servicio",
    "timeout",
    "latenc",
    "visual",
    "interfaz",
    "dashboard",
    "render",
    "login",
    "token",
    "sesion",
    "otp",
    "valid",
    "campo",
    "datos",
    "mensaje",
    "correo",
    "sms",
    "notific",
    "senda",
    "sit",
    "host",
    "liquidez",
    "saldo",
    "nomina",
)
_GENERIC_PATH_SEGMENTS: set[str] = {
    "pagos",
    "monetarias",
    "transferencias",
    "transferencia",
    "login y acceso",
    "credito",
    "senda bnc",
    "bbva mx",
    "sit",
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


def _root_cause_text_segments(
    summary: object,
    description: object | None = None,
) -> tuple[str, str]:
    summary_txt = _normalize_text(summary)
    description_txt = _normalize_text(description)
    return summary_txt, description_txt


def _root_cause_scores_weighted(
    summary_txt: str,
    description_txt: str,
) -> dict[str, int]:
    scores: dict[str, int] = {}
    for label, score in _root_cause_scores(summary_txt).items():
        scores[label] = scores.get(label, 0) + (int(score) * 3)
    for label, score in _root_cause_scores(description_txt).items():
        scores[label] = scores.get(label, 0) + (int(score) * 2)
    combined_text = " ".join(
        part for part in (summary_txt, description_txt) if str(part or "").strip()
    ).strip()
    for label, score in _root_cause_scores(combined_text).items():
        scores[label] = scores.get(label, 0) + int(score)
    return {label: score for label, score in scores.items() if int(score) > 0}


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
        return f"{_FALLBACK_THEME_PREFIX}{theme}"
    return _ROOT_CAUSE_FALLBACK_LABEL


def _has_semantic_hint(segment: str) -> bool:
    words = [w for w in str(segment or "").split() if w]
    if not words:
        return False
    return any(any(word.startswith(hint) for hint in _SEMANTIC_HINT_TOKENS) for word in words)


def _extract_semantic_phrase(
    summary: object,
    *,
    description: object | None = None,
) -> str:
    summary_txt, description_txt = _root_cause_text_segments(summary, description)
    text = " | ".join(part for part in (summary_txt, description_txt) if part).strip()
    if not text:
        return ""
    parts = [part.strip() for part in re.split(r"[|/;>\n]+", text) if part.strip()]
    for part in parts:
        cleaned = re.sub(r"\b(?:inc|mexbmi1|sksemex)[a-z0-9-]*\b", " ", part)
        cleaned = re.sub(r"\b\d+\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned or cleaned in _GENERIC_PATH_SEGMENTS:
            continue
        words = [w for w in cleaned.split() if w not in _ROOT_CAUSE_STOPWORDS and len(w) >= 2]
        if len(words) < 2:
            continue
        candidate = " ".join(words[:6]).strip()
        if not candidate or candidate in _GENERIC_PATH_SEGMENTS:
            continue
        if not _has_semantic_hint(candidate):
            continue
        return candidate
    return ""


def _format_semantic_phrase_label(phrase: str) -> str:
    words = [w for w in str(phrase or "").split() if w]
    if not words:
        return ""
    minor = {"de", "del", "la", "el", "y", "en", "a", "por", "con"}
    formatted: list[str] = []
    for idx, word in enumerate(words):
        if idx > 0 and word in minor:
            formatted.append(word)
            continue
        formatted.append(word.capitalize())
    label = " ".join(formatted).strip()
    return label[:48].rstrip()


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


def infer_root_cause_label(
    summary: object,
    *,
    description: object | None = None,
    theme_hint: str | None = None,
) -> str:
    summary_txt, description_txt = _root_cause_text_segments(summary, description)
    if not summary_txt and not description_txt:
        return _fallback_root_cause_label(summary, theme_hint=theme_hint)

    clean_summary = re.sub(r"\[[^\]]*\]", " ", summary_txt)
    clean_summary = re.sub(r"\([^)]*\)", " ", clean_summary)
    clean_summary = re.sub(r"\s+", " ", clean_summary).strip()
    clean_description = re.sub(r"\[[^\]]*\]", " ", description_txt)
    clean_description = re.sub(r"\([^)]*\)", " ", clean_description)
    clean_description = re.sub(r"\s+", " ", clean_description).strip()

    if not clean_summary and not clean_description:
        return _fallback_root_cause_label(summary, theme_hint=theme_hint)

    scores = _root_cause_scores_weighted(clean_summary, clean_description)
    best = _best_root_cause_label(scores)
    if best:
        return best
    fallback = _fallback_root_cause_label(summary, theme_hint=theme_hint)
    phrase_label = _format_semantic_phrase_label(
        _extract_semantic_phrase(clean_summary, description=clean_description)
    )
    if phrase_label:
        return phrase_label
    return fallback


def build_root_cause_labels(
    summaries: Sequence[object],
    *,
    descriptions: Sequence[object] | None = None,
    theme_hints: Sequence[str] | None = None,
) -> tuple[str, ...]:
    summary_values = [str(summary or "") for summary in list(summaries or [])]
    description_values = [str(desc or "") for desc in list(descriptions or [])]
    theme_hint_values = [str(hint or "") for hint in list(theme_hints or [])]

    labels: list[str] = []
    for idx, summary_txt in enumerate(summary_values):
        description_txt = description_values[idx] if idx < len(description_values) else ""
        theme_hint = theme_hint_values[idx] if idx < len(theme_hint_values) else ""
        labels.append(
            infer_root_cause_label(
                summary_txt,
                description=description_txt,
                theme_hint=theme_hint,
            )
        )
    return tuple(labels)


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
    descriptions: Sequence[object] | None = None,
    theme_hints: Sequence[str] | None = None,
    top_k: int = 3,
) -> tuple[RootCauseRank, ...]:
    labels = [
        str(label or "").strip()
        for label in build_root_cause_labels(
            summaries,
            descriptions=descriptions,
            theme_hints=theme_hints,
        )
    ]
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
            else pd.Timestamp.now("UTC").tz_localize(None).normalize()
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
            descriptions = (
                sub["description"].fillna("").astype(str).tolist()
                if "description" in sub.columns
                else None
            )
            roots_by_topic[topic_name] = summarize_root_causes(
                sub["summary"].fillna("").astype(str).tolist(),
                descriptions=descriptions,
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
