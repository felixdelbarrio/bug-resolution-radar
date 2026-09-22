"""Persistence and effective resolution for editable functionality taxonomies."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from bug_resolution_radar.config import (
    FUNCTIONALITY_TAXONOMY_ENV_BY_COUNTRY,
    Settings,
    config_home,
    default_functionality_taxonomy_for_country,
    normalize_country_name,
    validate_functionality_taxonomy,
)

FunctionalityTaxonomy = tuple[tuple[str, tuple[str, ...]], ...]
_OVERRIDES_FILENAME = "functionality_taxonomy_overrides.json"


def functionality_taxonomy_overrides_path() -> Path:
    return config_home() / "data" / _OVERRIDES_FILENAME


def _canonical_country(country: object) -> str:
    canonical = normalize_country_name(
        country,
        supported=list(FUNCTIONALITY_TAXONOMY_ENV_BY_COUNTRY),
    )
    if not canonical:
        raise ValueError(f"Geografía sin taxonomía funcional configurada: {country!s}")
    return canonical


def _revision(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
        return str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return str(path.resolve()), -1, -1


@lru_cache(maxsize=8)
def _load_overrides_cached(path_text: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns, size
    path = Path(path_text)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer la configuración de taxonomías: {exc}") from exc
    overrides = payload.get("overrides") if isinstance(payload, dict) else None
    if not isinstance(overrides, dict):
        raise ValueError("La configuración persistida de taxonomías es inválida")
    return dict(overrides)


def _load_overrides() -> dict[str, Any]:
    path = functionality_taxonomy_overrides_path()
    return dict(_load_overrides_cached(*_revision(path)))


def _serialize_taxonomy(taxonomy: FunctionalityTaxonomy) -> list[dict[str, Any]]:
    return [{"label": label, "keywords": list(keywords)} for label, keywords in taxonomy]


def functionality_taxonomy_revision_token() -> tuple[str, int, int]:
    return _revision(functionality_taxonomy_overrides_path())


def functionality_taxonomy_payload(settings: Settings, country: object) -> dict[str, Any]:
    canonical = _canonical_country(country)
    raw_override = _load_overrides().get(canonical)
    if raw_override is not None:
        taxonomy = validate_functionality_taxonomy(
            f"override de taxonomía para {canonical}", raw_override
        )
        source = "override"
    else:
        taxonomy = default_functionality_taxonomy_for_country(settings, canonical)
        source = "default"
    return {
        "country": canonical,
        "taxonomy": _serialize_taxonomy(taxonomy),
        "source": source,
    }


def effective_functionality_taxonomy(
    settings: Settings,
    country: object,
) -> FunctionalityTaxonomy:
    payload = functionality_taxonomy_payload(settings, country)
    return tuple(
        (str(row["label"]), tuple(str(keyword) for keyword in row["keywords"]))
        for row in payload["taxonomy"]
    )


def _write_overrides(overrides: dict[str, Any]) -> None:
    path = functionality_taxonomy_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    payload = {"overrides": overrides}
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    _load_overrides_cached.cache_clear()


def save_functionality_taxonomy_override(
    settings: Settings,
    country: object,
    taxonomy_value: object,
) -> dict[str, Any]:
    canonical = _canonical_country(country)
    taxonomy = validate_functionality_taxonomy(f"taxonomía para {canonical}", taxonomy_value)
    overrides = _load_overrides()
    overrides[canonical] = _serialize_taxonomy(taxonomy)
    _write_overrides(overrides)
    return functionality_taxonomy_payload(settings, canonical)


def reset_functionality_taxonomy_override(
    settings: Settings,
    country: object,
) -> dict[str, Any]:
    canonical = _canonical_country(country)
    overrides = _load_overrides()
    if canonical in overrides:
        del overrides[canonical]
        _write_overrides(overrides)
    return functionality_taxonomy_payload(settings, canonical)
