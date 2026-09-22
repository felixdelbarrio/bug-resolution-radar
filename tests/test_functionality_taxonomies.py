from __future__ import annotations

import importlib
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bug_resolution_radar.analytics.issue_functionality import classify_issue_functionality
from bug_resolution_radar.config import (
    FUNCTIONALITY_TAXONOMY_MAX_CATEGORIES,
    FUNCTIONALITY_TAXONOMY_MAX_KEYWORDS,
    Settings,
    validate_functionality_taxonomy,
)

taxonomy_service = importlib.import_module("bug_resolution_radar.services.functionality_taxonomies")
api_app = importlib.import_module("bug_resolution_radar.api.app")


@pytest.fixture(autouse=True)
def isolated_taxonomy_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "functionality_taxonomy_overrides.json"
    monkeypatch.setattr(taxonomy_service, "functionality_taxonomy_overrides_path", lambda: path)
    taxonomy_service._load_overrides_cached.cache_clear()
    return path


def _settings() -> Settings:
    return Settings(
        FUNCTIONALITY_TAXONOMY_SPAIN=json.dumps(
            [{"label": "Transferencias", "keywords": ["transferencia"]}],
            ensure_ascii=False,
        )
    )


def test_effective_taxonomy_uses_default_without_override() -> None:
    payload = taxonomy_service.functionality_taxonomy_payload(_settings(), "España")

    assert payload == {
        "country": "España",
        "taxonomy": [{"label": "Transferencias", "keywords": ["transferencia"]}],
        "source": "default",
    }


def test_save_and_read_valid_override(isolated_taxonomy_store: Path) -> None:
    settings = _settings()
    override = [{"label": "Canal QR", "keywords": ["Nómina QR"]}]

    saved = taxonomy_service.save_functionality_taxonomy_override(settings, "espana", override)
    loaded = taxonomy_service.functionality_taxonomy_payload(settings, "España")

    assert saved == loaded
    assert loaded["source"] == "override"
    assert loaded["taxonomy"] == override
    assert (
        json.loads(isolated_taxonomy_store.read_text(encoding="utf-8"))["overrides"]["España"]
        == override
    )
    assert not isolated_taxonomy_store.with_suffix(".json.tmp").exists()


def test_reset_removes_only_override_and_returns_default(
    isolated_taxonomy_store: Path,
) -> None:
    settings = _settings()
    taxonomy_service.save_functionality_taxonomy_override(
        settings,
        "España",
        [{"label": "Canal QR", "keywords": ["qr"]}],
    )

    payload = taxonomy_service.reset_functionality_taxonomy_override(settings, "España")

    assert payload["source"] == "default"
    assert payload["taxonomy"][0]["label"] == "Transferencias"
    stored = json.loads(isolated_taxonomy_store.read_text(encoding="utf-8"))
    assert "España" not in stored["overrides"]


@pytest.mark.parametrize(
    ("taxonomy", "message"),
    [
        (
            [
                {"label": "Nómina", "keywords": ["uno"]},
                {"label": "Nomina", "keywords": ["dos"]},
            ],
            "label duplicado",
        ),
        ([{"label": "Otros", "keywords": ["otro"]}], "categoría reservada"),
        ([{"label": "Pagos", "keywords": [""]}], "strings no vacíos"),
        ([{"label": "Pagos", "keywords": ["pago", "PÁGO"]}], "duplicados"),
    ],
)
def test_validator_rejects_invalid_categories(
    taxonomy: list[dict[str, object]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_functionality_taxonomy("taxonomía", taxonomy)


@pytest.mark.parametrize(
    "taxonomy",
    [
        [
            {"label": f"Categoría {index}", "keywords": [f"keyword {index}"]}
            for index in range(FUNCTIONALITY_TAXONOMY_MAX_CATEGORIES + 1)
        ],
        [
            {
                "label": "Categoría",
                "keywords": [
                    f"keyword {index}" for index in range(FUNCTIONALITY_TAXONOMY_MAX_KEYWORDS + 1)
                ],
            }
        ],
        [{"label": "x" * 101, "keywords": ["keyword"]}],
        [{"label": "Categoría", "keywords": ["x" * 151]}],
    ],
)
def test_validator_rejects_size_limits(taxonomy: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError, match="máximo|supera"):
        validate_functionality_taxonomy("taxonomía", taxonomy)


def test_new_category_requires_no_classifier_code_change() -> None:
    settings = _settings()
    taxonomy_service.save_functionality_taxonomy_override(
        settings,
        "España",
        [{"label": "Canal Holográfico", "keywords": ["holograma"]}],
    )

    result = classify_issue_functionality(
        pd.Series({"country": "España", "summary": "Falla el holograma corporativo"}),
        settings=settings,
    )

    assert result == "Canal Holográfico"


def test_classifier_uses_modified_priority_and_keeps_other_implicit() -> None:
    settings = _settings()
    taxonomy_service.save_functionality_taxonomy_override(
        settings,
        "España",
        [
            {"label": "Primera", "keywords": ["señal común"]},
            {"label": "Segunda", "keywords": ["señal común", "otra señal"]},
        ],
    )

    matched = classify_issue_functionality(
        pd.Series({"country": "España", "summary": "Existe una señal común"}),
        settings=settings,
    )
    unmatched = classify_issue_functionality(
        pd.Series({"country": "España", "summary": "Sin coincidencias"}),
        settings=settings,
    )

    assert matched == "Primera"
    assert unmatched == "Otros"


def test_api_get_put_and_reset_use_one_document_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)
    client = TestClient(api_app.create_app())

    initial = client.get("/api/functionality-taxonomies/Espa%C3%B1a")
    updated = client.put(
        "/api/functionality-taxonomies/Espa%C3%B1a",
        json={"taxonomy": [{"label": "Canal QR", "keywords": ["qr"]}]},
    )
    restored = client.delete("/api/functionality-taxonomies/Espa%C3%B1a")

    assert initial.status_code == 200
    assert initial.json()["source"] == "default"
    assert updated.status_code == 200
    assert updated.json()["taxonomy"] == [{"label": "Canal QR", "keywords": ["qr"]}]
    assert restored.status_code == 200
    assert restored.json()["source"] == "default"


def test_api_exposes_backend_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_app, "load_settings", _settings)
    response = TestClient(api_app.create_app()).put(
        "/api/functionality-taxonomies/Espa%C3%B1a",
        json={"taxonomy": [{"label": "Otros", "keywords": ["otro"]}]},
    )

    assert response.status_code == 400
    assert "reservada" in response.json()["detail"]


def test_parallel_updates_preserve_each_country(isolated_taxonomy_store: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    settings = _settings()
    countries = ["España", "México", "Perú", "Colombia", "Argentina"]
    taxonomy = [{"label": "Canal QR", "keywords": ["qr"]}]
    with ThreadPoolExecutor(max_workers=len(countries)) as executor:
        results = list(
            executor.map(
                lambda country: taxonomy_service.save_functionality_taxonomy_override(
                    settings, country, taxonomy
                ),
                countries,
            )
        )
    assert {row["country"] for row in results} == set(countries)
    for country in countries:
        assert (
            taxonomy_service.functionality_taxonomy_payload(settings, country)["taxonomy"]
            == taxonomy
        )


def test_report_cache_changes_on_taxonomy_edit_and_reset() -> None:
    from bug_resolution_radar.reports.executive_ppt import _report_request_cache_key

    settings = _settings()

    def cache_key() -> str:
        return _report_request_cache_key(
            settings,
            country="España",
            source_id="jira:espana:core",
            status_filters=None,
            priority_filters=None,
            assignee_filters=None,
            dff_override=None,
        )

    original = cache_key()
    taxonomy_service.save_functionality_taxonomy_override(
        settings, "España", [{"label": "Canal QR", "keywords": ["qr"]}]
    )
    edited = cache_key()
    assert edited != original
    taxonomy_service.reset_functionality_taxonomy_override(settings, "España")
    assert cache_key() != edited
    before_default_change = cache_key()
    settings.FUNCTIONALITY_TAXONOMY_SPAIN = json.dumps(
        [{"label": "Nuevo default", "keywords": ["canal"]}]
    )
    assert cache_key() != before_default_change
