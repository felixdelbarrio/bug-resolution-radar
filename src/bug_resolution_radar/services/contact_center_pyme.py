"""Local, country-specific Contact Center PYME configuration."""

from __future__ import annotations

import os
import re
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator

from bug_resolution_radar.config import (
    Settings,
    config_home,
    normalize_country_name,
    supported_countries,
)

_FILENAME = "contact_center_pyme.json"
_LOCK = Lock()


class ContactCenterPerson(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    legajo: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    mail: str = Field(min_length=1, max_length=254)

    @field_validator("mail")
    @classmethod
    def validate_mail(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Correo no válido.")
        return value


class ContactCenterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool
    people: list[ContactCenterPerson] = Field(max_length=5000)

    @field_validator("people")
    @classmethod
    def validate_people(cls, people: list[ContactCenterPerson]) -> list[ContactCenterPerson]:
        for field in ("legajo", "mail"):
            tokens = [getattr(person, field).casefold() for person in people]
            if len(tokens) != len(set(tokens)):
                label = "usuario" if field == "legajo" else "correo"
                raise ValueError(f"No se permiten valores duplicados de {label}.")
        return people


class ContactCenterPayload(ContactCenterConfig):
    country: str


class ContactCenterStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    countries: dict[str, ContactCenterConfig] = Field(default_factory=dict)


class ContactCenterStorageError(RuntimeError):
    """The persisted configuration could not be read or written safely."""


def contact_center_pyme_path() -> Path:
    return config_home() / "data" / _FILENAME


def _canonical_country(settings: Settings, country: str) -> str:
    canonical = normalize_country_name(country, supported=supported_countries(settings))
    if not canonical:
        raise ValueError("Geografía no soportada.")
    return canonical


def _read_store(path: Path) -> ContactCenterStore:
    try:
        return ContactCenterStore.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ContactCenterStore()
    except (OSError, ValidationError, UnicodeError) as exc:
        raise ContactCenterStorageError(
            "No se pudo leer la configuración de Contact Center PYME."
        ) from exc


def _write_store(path: Path, store: ContactCenterStore) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".contact_center_pyme-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(store.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except OSError as exc:
        raise ContactCenterStorageError(
            "No se pudo guardar la configuración de Contact Center PYME."
        ) from exc
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def _payload(country: str, config: ContactCenterConfig) -> ContactCenterPayload:
    return ContactCenterPayload(country=country, enabled=config.enabled, people=config.people)


def _country_config(store: ContactCenterStore, country: str) -> ContactCenterConfig:
    config = store.countries.get(country)
    if config is not None:
        return config
    return ContactCenterConfig(enabled=country == "Argentina", people=[])


def contact_center_enabled_countries(settings: Settings) -> list[str]:
    """Expose only the activation flag, never operator data."""
    store = _read_store(contact_center_pyme_path())
    return [
        country
        for country in supported_countries(settings)
        if _country_config(store, country).enabled
    ]


def contact_center_pyme_payload(settings: Settings, country: str) -> ContactCenterPayload:
    canonical = _canonical_country(settings, country)
    store = _read_store(contact_center_pyme_path())
    return _payload(canonical, _country_config(store, canonical))


def save_contact_center_pyme(
    settings: Settings, country: str, config: ContactCenterConfig
) -> ContactCenterPayload:
    canonical = _canonical_country(settings, country)
    path = contact_center_pyme_path()
    with _LOCK:
        store = _read_store(path)
        store.countries[canonical] = config
        _write_store(path, store)
    return _payload(canonical, config)
