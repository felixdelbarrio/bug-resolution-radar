"""Semantic status/priority colors shared across backend and UI."""

from __future__ import annotations

import re
from typing import Dict, Iterable, Optional

from bug_resolution_radar.theme.design_tokens import (
    BBVA_GOAL_ACCENT_7,
    BBVA_GOAL_SURFACE_8,
    BBVA_NEUTRAL_SOFT,
    BBVA_SIGNAL_GREEN_1,
    BBVA_SIGNAL_GREEN_2,
    BBVA_SIGNAL_GREEN_3,
    BBVA_SIGNAL_ORANGE_2,
    BBVA_SIGNAL_RED_1,
    BBVA_SIGNAL_RED_2,
    BBVA_SIGNAL_RED_3,
    BBVA_SIGNAL_YELLOW_1,
)


def normalize_semantic_token(value: Optional[str]) -> str:
    txt = str(value or "").strip().lower()
    txt = txt.replace("_", " ").replace("-", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


STATUS_COLOR_BY_KEY: Dict[str, str] = {
    "new": BBVA_SIGNAL_RED_3,
    "ready": BBVA_SIGNAL_RED_3,
    "analysing": BBVA_SIGNAL_RED_3,
    "blocked": BBVA_SIGNAL_RED_3,
    "en progreso": BBVA_SIGNAL_ORANGE_2,
    "in progress": BBVA_SIGNAL_ORANGE_2,
    "to rework": BBVA_SIGNAL_ORANGE_2,
    "rework": BBVA_SIGNAL_ORANGE_2,
    "test": BBVA_SIGNAL_ORANGE_2,
    "ready to verify": BBVA_SIGNAL_ORANGE_2,
    "accepted": BBVA_SIGNAL_GREEN_3,
    "ready to deploy": BBVA_SIGNAL_GREEN_3,
    "deployed": BBVA_GOAL_ACCENT_7,
    "closed": BBVA_SIGNAL_GREEN_1,
    "resolved": BBVA_SIGNAL_GREEN_1,
    "done": BBVA_SIGNAL_GREEN_1,
    "open": BBVA_SIGNAL_YELLOW_1,
    "created": BBVA_SIGNAL_RED_3,
}

PRIORITY_COLOR_BY_KEY: Dict[str, str] = {
    "supone un impedimento": BBVA_SIGNAL_RED_1,
    "highest": BBVA_SIGNAL_RED_1,
    "high": BBVA_SIGNAL_RED_2,
    "medium": BBVA_SIGNAL_ORANGE_2,
    "low": BBVA_SIGNAL_GREEN_2,
    "lowest": BBVA_SIGNAL_GREEN_1,
}


def status_color(status: Optional[str]) -> str:
    return STATUS_COLOR_BY_KEY.get(normalize_semantic_token(status), BBVA_NEUTRAL_SOFT)


def priority_color(priority: Optional[str]) -> str:
    return PRIORITY_COLOR_BY_KEY.get(normalize_semantic_token(priority), BBVA_NEUTRAL_SOFT)


def status_color_map(statuses: Optional[Iterable[str]] = None) -> Dict[str, str]:
    if statuses is None:
        return {}
    return {str(status): status_color(str(status)) for status in statuses}


def flow_signal_color_map() -> Dict[str, str]:
    return {
        "created": BBVA_SIGNAL_RED_3,
        "closed": BBVA_SIGNAL_GREEN_2,
        "resolved": BBVA_SIGNAL_GREEN_2,
        "deployed": BBVA_GOAL_ACCENT_7,
        "open": BBVA_SIGNAL_YELLOW_1,
        "open_backlog_proxy": BBVA_SIGNAL_YELLOW_1,
    }


def priority_color_map() -> Dict[str, str]:
    return {
        "Supone un impedimento": BBVA_SIGNAL_RED_1,
        "Highest": BBVA_SIGNAL_RED_1,
        "High": BBVA_SIGNAL_RED_2,
        "Medium": BBVA_SIGNAL_ORANGE_2,
        "Low": BBVA_SIGNAL_GREEN_2,
        "Lowest": BBVA_SIGNAL_GREEN_1,
        "(sin priority)": BBVA_NEUTRAL_SOFT,
        "": BBVA_NEUTRAL_SOFT,
    }


def semantic_color_contract() -> Dict[str, object]:
    """Return the frontend-consumable semantic token contract."""
    return {
        "statusByKey": dict(STATUS_COLOR_BY_KEY),
        "priorityByKey": dict(PRIORITY_COLOR_BY_KEY),
        "neutral": BBVA_NEUTRAL_SOFT,
        "goalAccent": BBVA_GOAL_ACCENT_7,
        "goalSurface": BBVA_GOAL_SURFACE_8,
    }
