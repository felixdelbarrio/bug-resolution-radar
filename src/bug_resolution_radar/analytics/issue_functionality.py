"""Centralized, geography-aware issue functionality classification."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Pattern, Sequence

import pandas as pd

from bug_resolution_radar.analytics.functionality_normalization import (
    normalize_functionality_text,
)
from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.functionality_taxonomies import (
    effective_functionality_taxonomy,
)

FUNCTIONALITY_COL = "functionality"
HELIX_EXECUTIVE_DESCRIPTION_COL = "helix_executive_description"
_DESCRIPTION_COL = "description"
_FALLBACK_FUNCTIONALITY = "Otros"
_DEFAULT_COUNTRY = "México"

FunctionalityTaxonomy = tuple[tuple[str, tuple[str, ...]], ...]
CompiledFunctionalityTaxonomy = tuple[tuple[str, Pattern[str]], ...]


@lru_cache(maxsize=32)
def _compile_taxonomy(taxonomy: FunctionalityTaxonomy) -> CompiledFunctionalityTaxonomy:
    return tuple(
        (
            label,
            re.compile(
                r"(?<!\w)(?:"
                + "|".join(re.escape(normalize_functionality_text(keyword)) for keyword in keywords)
                + r")(?!\w)"
            ),
        )
        for label, keywords in taxonomy
    )


def classify_functionality_text(
    text: object,
    *,
    taxonomy: FunctionalityTaxonomy,
    default: str = _FALLBACK_FUNCTIONALITY,
) -> str:
    """Classify normalized issue text; the first configured category match wins."""
    normalized = normalize_functionality_text(text)
    if not normalized:
        return default
    for label, pattern in _compile_taxonomy(taxonomy):
        if pattern.search(normalized):
            return label
    return default


def _text_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype=str)
    return df[column].fillna("").astype(str).str.strip()


def build_issue_classification_text(df: pd.DataFrame) -> pd.Series:
    """Build functional text only from normalized descriptive issue fields."""
    parts = [
        _text_series(df, "summary"),
        _text_series(df, _DESCRIPTION_COL),
        _text_series(df, HELIX_EXECUTIVE_DESCRIPTION_COL),
    ]
    combined = parts[0]
    for part in parts[1:]:
        combined = combined.str.cat(part, sep=" ")
    return combined.str.replace(r"\s+", " ", regex=True).str.strip()


def functionality_order(
    settings: Settings,
    *,
    country: object,
    include_other: bool = False,
) -> tuple[str, ...]:
    labels = tuple(label for label, _ in effective_functionality_taxonomy(settings, country))
    return labels + ((_FALLBACK_FUNCTIONALITY,) if include_other else ())


def classify_issue_functionality(
    issue: pd.Series,
    *,
    settings: Settings | None = None,
    country: object = "",
) -> str:
    """Classify one normalized issue with the taxonomy selected by geography."""
    frame = pd.DataFrame([issue])
    text = build_issue_classification_text(frame).iloc[0]
    issue_country = country or issue.get("country", "") or _DEFAULT_COUNTRY
    taxonomy = effective_functionality_taxonomy(settings or Settings(), issue_country)
    return classify_functionality_text(text, taxonomy=taxonomy)


def ensure_issue_functionality_columns(
    df: pd.DataFrame | None,
    *,
    settings: Settings | None = None,
    country: object = "",
    functionality_col: str = FUNCTIONALITY_COL,
    theme_col: str | None = None,
) -> pd.DataFrame:
    """Classify each normalized issue once and expose shared functionality columns."""
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    if df.empty:
        return df.copy(deep=False)

    work = df.copy(deep=False)
    target_col = str(theme_col or functionality_col or FUNCTIONALITY_COL).strip()
    if functionality_col and functionality_col in work.columns:
        existing_functionality = _text_series(work, functionality_col)
        if existing_functionality.ne("").all():
            if target_col and target_col != functionality_col:
                work[target_col] = existing_functionality.to_numpy(copy=False)
            return work
    if target_col and target_col in work.columns:
        existing = _text_series(work, target_col)
        if existing.ne("").all():
            if functionality_col and functionality_col not in work.columns:
                work[functionality_col] = existing.to_numpy(copy=False)
            return work

    active_settings = settings or Settings()
    texts = build_issue_classification_text(work).tolist()
    if country:
        countries: Sequence[object] = [country] * len(work)
    elif "country" in work.columns:
        countries = work["country"].fillna("").astype(str).tolist()
    else:
        countries = [_DEFAULT_COUNTRY] * len(work)

    taxonomy_by_country: dict[str, FunctionalityTaxonomy] = {}
    classified: list[str] = []
    for text, raw_country in zip(texts, countries):
        country_key = str(raw_country or _DEFAULT_COUNTRY).strip() or _DEFAULT_COUNTRY
        taxonomy = taxonomy_by_country.get(country_key)
        if taxonomy is None:
            taxonomy = effective_functionality_taxonomy(active_settings, country_key)
            taxonomy_by_country[country_key] = taxonomy
        classified.append(classify_functionality_text(text, taxonomy=taxonomy))

    values = pd.Series(classified, index=work.index, dtype=str)
    if functionality_col:
        work[functionality_col] = values.to_numpy(copy=False)
    if theme_col and theme_col != functionality_col:
        work[theme_col] = values.to_numpy(copy=False)
    return work
