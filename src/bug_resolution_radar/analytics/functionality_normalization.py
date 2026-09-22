"""Shared normalization for functional taxonomy validation and matching."""

from __future__ import annotations

import unicodedata


def normalize_functionality_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())
