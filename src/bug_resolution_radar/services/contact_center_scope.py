"""Single business rule for country-specific, complementary Contact Center scopes."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from bug_resolution_radar.common.submitter import submitter_login
from bug_resolution_radar.config import Settings, normalize_country_name
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.services.contact_center_pyme import (
    contact_center_pyme_path,
    contact_center_pyme_payload,
)

CONTACT_CENTERS = ("PYME", "BEI")


def contact_center_revision() -> tuple[str, int, int]:
    path = contact_center_pyme_path().resolve()
    try:
        stat = path.stat()
        return (str(path), stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        return (str(path), -1, -1)


def _token(value: object) -> str:
    return str(value).strip().casefold() if isinstance(value, str) else ""


def active_contact_center(settings: Settings, country: str, selection: str) -> str:
    """Empty is the explicitly unfiltered transport/legacy contract."""
    selected = str(selection or "").strip().upper()
    if not selected:
        return ""
    if selected not in CONTACT_CENTERS:
        raise ValueError("Contact center debe ser PYME o BEI.")
    canonical = normalize_country_name(country, settings=settings)
    if not canonical:
        return ""
    return selected if contact_center_pyme_payload(settings, canonical).enabled else ""


@lru_cache(maxsize=8)
def _legacy_helix_submitters(
    path: str, mtime_ns: int, size: int
) -> dict[tuple[str, str, str], str]:
    """Recover the source field from the raw cache for pre-migration issues."""
    del mtime_ns, size
    document = HelixRepo(Path(path)).load()
    if document is None:
        return {}
    out: dict[tuple[str, str, str], str] = {}
    for item in document.items:
        identity = (_token(item.country), _token(item.source_id), _token(item.id))
        login = _token(item.submitter or submitter_login(item.raw_fields))
        if all(identity) and login:
            out[identity] = login
    return out


def _legacy_submitters(settings: Settings) -> dict[tuple[str, str, str], str]:
    path = Path(settings.HELIX_DATA_PATH).expanduser().resolve()
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {}
    return _legacy_helix_submitters(str(path), stat.st_mtime_ns, stat.st_size)


def apply_contact_center_filter(
    frame: pd.DataFrame, *, settings: Settings, country: str, selection: str
) -> pd.DataFrame:
    """Partition BEFORE analytical filters; only enabled countries are affected.

    A missing/blank Submitter is a non-match (BEI). Never fall back to a name,
    e-mail, assignee or Jira reporter; the roster's persisted legajo is Usuario.
    """
    if frame.empty:
        return frame
    selected = active_contact_center(settings, country, selection)
    if not selected:
        return frame
    roster = contact_center_pyme_payload(settings, country)
    users = {_token(person.legajo) for person in roster.people} - {""}
    if "submitter" in frame.columns:
        submitters = frame["submitter"].map(_token)
    elif "Submitter" in frame.columns:
        submitters = frame["Submitter"].map(_token)
    else:
        submitters = pd.Series("", index=frame.index, dtype=object)
    # An old normalized Helix issue may not yet have a Submitter column/value.
    required = {"country", "source_id", "key", "source_type"}
    if required.issubset(frame.columns):
        missing = submitters.eq("") & frame["source_type"].map(_token).eq("helix")
        if missing.any():
            lookup = _legacy_submitters(settings)
            identities = zip(
                frame.loc[missing, "country"].map(_token),
                frame.loc[missing, "source_id"].map(_token),
                frame.loc[missing, "key"].map(_token),
            )
            submitters = submitters.copy()
            submitters.loc[missing] = [lookup.get(identity, "") for identity in identities]
    matches = submitters.isin(users)
    return frame.loc[matches if selected == "PYME" else ~matches].copy(deep=False)
