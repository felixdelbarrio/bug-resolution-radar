from __future__ import annotations

import json

import pandas as pd
import pytest
from pydantic import ValidationError

from bug_resolution_radar.analytics.insights import build_theme_fortnight_trend
from bug_resolution_radar.analytics.issue_functionality import (
    classify_issue_functionality,
    ensure_issue_functionality_columns,
    functionality_order,
)
from bug_resolution_radar.config import Settings


@pytest.mark.parametrize(
    ("country", "text", "expected"),
    [
        ("México", "problema en pago de nómina", "Pagos y nómina"),
        ("México", "error en transferencia SPEI", "Transferencias"),
        ("Argentina", "no puede activar token digital", "Acceso, claves y token"),
        ("Argentina", "problema en bandeja eCheq", "eCheq y cheques"),
        ("España", "rechazo al firmar fichero de nóminas", "Ficheros y remesas"),
        ("Perú", "error en pagos masivos online", "Pagos y pagos masivos"),
        ("Colombia", "timeout HTTP 503 en middleware", "Otros"),
        ("México", "NÓMINA no disponible", "Pagos y nómina"),
        ("México", "evento técnico sin señal", "Otros"),
    ],
)
def test_default_taxonomies_classify_by_geography(
    country: str,
    text: str,
    expected: str,
) -> None:
    issue = pd.Series({"country": country, "summary": text})
    assert classify_issue_functionality(issue, settings=Settings()) == expected


def test_custom_category_is_loaded_only_from_environment_setting() -> None:
    custom = json.dumps(
        [{"label": "Canal QR", "keywords": ["qr empresarial"]}],
        ensure_ascii=False,
    )
    settings = Settings(FUNCTIONALITY_TAXONOMY_COLOMBIA=custom)
    issue = pd.Series({"country": "Colombia", "summary": "Falla en QR empresarial"})

    assert classify_issue_functionality(issue, settings=settings) == "Canal QR"
    assert functionality_order(settings, country="colombia") == ("Canal QR",)


def test_description_participates_when_summary_has_no_functional_semantics() -> None:
    frame = pd.DataFrame(
        [
            {
                "country": "España",
                "summary": "SF-004821",
                "description": "El usuario no puede firmar la remesa",
            }
        ]
    )

    classified = ensure_issue_functionality_columns(frame, settings=Settings())

    assert classified.iloc[0]["functionality"] == "Ficheros y remesas"


@pytest.mark.parametrize(
    "invalid",
    [
        "not-json",
        "{}",
        '[{"label":"","keywords":["x"]}]',
        '[{"label":"A","keywords":[]}]',
        '[{"label":"A","keywords":["x"]},{"label":"A","keywords":["y"]}]',
    ],
)
def test_malformed_taxonomy_reports_the_environment_variable(invalid: str) -> None:
    with pytest.raises(ValidationError, match="FUNCTIONALITY_TAXONOMY_SPAIN"):
        Settings(FUNCTIONALITY_TAXONOMY_SPAIN=invalid)


def test_trend_reuses_classification_and_preserves_configured_order() -> None:
    settings = Settings()
    source = pd.DataFrame(
        {
            "created": ["2026-04-02", "2026-04-03", "2026-04-04"],
            "country": ["España", "España", "España"],
            "summary": ["pago rechazado", "transferencia rechazada", "HTTP 503"],
        }
    )
    classified = ensure_issue_functionality_columns(source, settings=settings, country="España")
    order = functionality_order(settings, country="España", include_other=True)

    trend = build_theme_fortnight_trend(
        classified,
        theme_whitelist=order,
        cumulative=True,
    )

    assert trend["tema"].drop_duplicates().tolist() == ["Transferencias", "Pagos", "Otros"]
