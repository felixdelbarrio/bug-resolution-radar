"""Shared normalization for functional taxonomy validation and matching."""

from __future__ import annotations

import unicodedata


def normalize_functionality_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    if not text.isascii():
        marks = {ord(char): None for char in set(text) if unicodedata.combining(char)}
        text = text.translate(marks)
    return " ".join(text.split())
