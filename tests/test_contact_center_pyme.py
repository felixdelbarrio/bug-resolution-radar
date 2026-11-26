"""Contract and persistence regression tests with synthetic operators only."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bug_resolution_radar.api import contact_center_pyme as api
from bug_resolution_radar.config import Settings
from bug_resolution_radar.services import contact_center_pyme as service


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(service, "config_home", lambda: tmp_path)
    monkeypatch.setattr(api, "load_settings", lambda: Settings())
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def sample() -> dict[str, str]:
    return {"legajo": "A001", "name": "Operador de prueba", "mail": "test@example.com"}


def test_initial_geographies(client: TestClient) -> None:
    for country in ("Argentina", "España", "México", "Colombia", "Perú"):
        response = client.get(f"/api/contact-center-pyme/{country}")
        assert response.status_code == 200
        assert response.json() == {
            "country": country,
            "enabled": country == "Argentina",
            "people": [],
        }
        assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/contact-center-pyme/NoExiste").status_code == 400
    assert client.get("/api/contact-center-pyme/Peru").json()["country"] == "Perú"


def test_seed_roundtrip_and_country_isolation(client: TestClient, tmp_path: Path) -> None:
    seed = service.ContactCenterStore(
        countries={
            "Argentina": service.ContactCenterConfig(
                enabled=True, people=[service.ContactCenterPerson(**sample())]
            )
        }
    )
    path = tmp_path / "data" / "contact_center_pyme.json"
    path.parent.mkdir()
    path.write_text(seed.model_dump_json(), encoding="utf-8")
    argentina = "/api/contact-center-pyme/Argentina"
    mexico = "/api/contact-center-pyme/México"
    assert client.get(argentina).json()["people"] == [sample()]
    person = {**sample(), "legajo": " B002 ", "name": " Prueba México "}
    response = client.put(mexico, json={"enabled": True, "people": [person]})
    assert response.status_code == 200
    assert response.json()["people"][0]["legajo"] == "B002"
    assert response.json()["people"][0]["name"] == "Prueba México"
    assert client.get(argentina).json()["people"] == [sample()]
    assert client.put(argentina, json={"enabled": False, "people": [sample()]}).status_code == 200
    assert client.get(argentina).json() == {
        "country": "Argentina",
        "enabled": False,
        "people": [sample()],
    }
    assert client.get(mexico).json()["enabled"] is True
    assert path.is_file()
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize(
    "people",
    [
        [{**sample(), "legajo": " "}],
        [{**sample(), "mail": "not-an-email"}],
        [sample(), {**sample(), "legajo": "a001", "mail": "other@example.com"}],
        [sample(), {**sample(), "legajo": "B002", "mail": "TEST@example.com"}],
    ],
)
def test_invalid_rows_do_not_write(client: TestClient, people: list[dict[str, str]]) -> None:
    response = client.put(
        "/api/contact-center-pyme/Argentina", json={"enabled": True, "people": people}
    )
    assert response.status_code == 422
    assert not service.contact_center_pyme_path().exists()


def test_corrupt_store_is_not_overwritten(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "data" / "contact_center_pyme.json"
    path.parent.mkdir()
    path.write_text("not-json", encoding="utf-8")
    endpoint = "/api/contact-center-pyme/Argentina"
    assert client.get(endpoint).status_code == 500
    assert client.put(endpoint, json={"enabled": True, "people": []}).status_code == 500
    assert path.read_text(encoding="utf-8") == "not-json"


def test_empty_list_is_persisted(client: TestClient) -> None:
    endpoint = "/api/contact-center-pyme/Argentina"
    assert client.put(endpoint, json={"enabled": True, "people": []}).status_code == 200
    assert client.get(endpoint).json()["people"] == []


def test_enabled_countries_follow_saved_flags_without_personal_data(client: TestClient) -> None:
    settings = Settings()
    assert service.contact_center_enabled_countries(settings) == ["Argentina"]
    assert (
        client.put(
            "/api/contact-center-pyme/Argentina", json={"enabled": False, "people": [sample()]}
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/contact-center-pyme/México", json={"enabled": True, "people": [sample()]}
        ).status_code
        == 200
    )
    assert service.contact_center_enabled_countries(settings) == ["México"]
    assert client.get("/api/contact-center-pyme/Argentina").json()["people"] == [sample()]
