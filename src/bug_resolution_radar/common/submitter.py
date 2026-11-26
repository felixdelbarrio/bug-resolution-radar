"""Read the source Submitter login, never a display name or reporter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def submitter_login(fields: Mapping[str, Any] | None) -> str:
    """Support the canonical ARSQL alias and the original field (case-insensitive)."""
    for key, value in (fields or {}).items():
        if str(key).strip().casefold() != "submitter":
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
