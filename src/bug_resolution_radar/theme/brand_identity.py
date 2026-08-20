"""Canonical BBVA corporate identity shared by UI and report generators."""

from __future__ import annotations

from typing import Final

CORPORATE_WORDMARK: Final[str] = "BBVA"
CORPORATE_DESCRIPTOR_LINES: Final[tuple[str, str]] = (
    "Banca de Empresas",
    "e Instituciones",
)
CORPORATE_BRAND_NAME: Final[str] = (
    f"{CORPORATE_WORDMARK} {' '.join(CORPORATE_DESCRIPTOR_LINES)}"
)


def frontend_brand_contract() -> dict[str, object]:
    """Return the immutable lockup copy consumed by the local React shell."""
    return {
        "name": CORPORATE_BRAND_NAME,
        "wordmark": CORPORATE_WORDMARK,
        "descriptorLines": list(CORPORATE_DESCRIPTOR_LINES),
    }
