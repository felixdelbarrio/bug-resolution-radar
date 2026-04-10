"""Common helpers for the UI layer built on backend/shared modules."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Tuple

from bug_resolution_radar.analytics.issues import normalize_text_col, open_issues_only, priority_rank
from bug_resolution_radar.models.schema import IssuesDocument
from bug_resolution_radar.repositories.issues_store import (
    df_from_issues_doc,
    load_issues_df,
    load_issues_doc,
    save_issues_doc,
)
from bug_resolution_radar.theme.design_tokens import (
    BBVA_GOAL_ACCENT_7,
    BBVA_GOAL_SURFACE_8,
    BBVA_NEUTRAL_SOFT,
    hex_to_rgba,
)
from bug_resolution_radar.theme.semantic_colors import (
    PRIORITY_COLOR_BY_KEY,
    STATUS_COLOR_BY_KEY,
    flow_signal_color_map,
    normalize_semantic_token,
    priority_color,
    priority_color_map,
    status_color,
    status_color_map,
)


def _css_attr_value(txt: str) -> str:
    return str(txt or "").replace("\\", "\\\\").replace('"', '\\"')


def _group_tokens_by_color(token_color_map: Dict[str, str]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for raw_token, raw_color in token_color_map.items():
        token = normalize_semantic_token(raw_token)
        color = str(raw_color or "").strip()
        if not token or not color:
            continue
        bucket = grouped.setdefault(color, [])
        if token not in bucket:
            bucket.append(token)
    return grouped


def _semantic_option_css_block(*, tokens: List[str], color: str) -> str:
    selectors: List[str] = []
    for token in list(tokens or []):
        txt = _css_attr_value(token)
        selectors.append(
            (
                'div[data-baseweb="popover"] '
                f'[role="option"]:is([aria-label*="{txt}" i], [title*="{txt}" i])'
            )
        )
    if not selectors:
        return ""
    selector_group = ",\n".join(selectors)
    return (
        f"{selector_group} {{\n"
        "  padding-left: 1.62rem !important;\n"
        f"  --bbva-opt-dot: {color};\n"
        f"  border-left: 2px solid color-mix(in srgb, {color} 72%, transparent);\n"
        "  background-image: radial-gradient(\n"
        "    circle at 0.80rem center,\n"
        "    var(--bbva-opt-dot) 0.24rem,\n"
        "    transparent 0.25rem\n"
        "  ) !important;\n"
        "  background-repeat: no-repeat !important;\n"
        "}\n"
    )


@lru_cache(maxsize=1)
def semantic_popover_css_rules() -> str:
    """Build semantic option CSS from central status/priority token maps."""
    blocks: List[str] = []
    for color, tokens in _group_tokens_by_color(STATUS_COLOR_BY_KEY).items():
        block = _semantic_option_css_block(tokens=tokens, color=color)
        if block:
            blocks.append(block)
    for color, tokens in _group_tokens_by_color(PRIORITY_COLOR_BY_KEY).items():
        block = _semantic_option_css_block(tokens=tokens, color=color)
        if block:
            blocks.append(block)
    return "\n".join(blocks)


def chip_tone_for_color(hex_color: str) -> Tuple[float, float]:
    """Return border/bg alpha tuple for chip rendering by semantic color."""
    normalized = str(hex_color or "").strip().upper()
    if normalized == BBVA_GOAL_ACCENT_7:
        return (0.78, 0.28)
    return (0.62, 0.16)


def chip_palette_for_color(hex_color: str) -> Tuple[str, str, str]:
    """Return (text_color, border_color, background_color) for chip rendering."""
    txt = str(hex_color or "").strip()
    normalized = txt.upper()
    if normalized == BBVA_GOAL_ACCENT_7:
        return (
            BBVA_GOAL_ACCENT_7,
            hex_to_rgba(BBVA_GOAL_ACCENT_7, 0.64, fallback=BBVA_NEUTRAL_SOFT),
            BBVA_GOAL_SURFACE_8,
        )
    border_alpha, bg_alpha = chip_tone_for_color(txt)
    return (
        txt,
        hex_to_rgba(txt, border_alpha, fallback=BBVA_NEUTRAL_SOFT),
        hex_to_rgba(txt, bg_alpha, fallback=BBVA_NEUTRAL_SOFT),
    )


def chip_style_from_color(hex_color: str) -> str:
    txt, border, bg = chip_palette_for_color(hex_color)
    return (
        f"color:{txt}; border:1px solid {border}; background:{bg}; "
        "border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.80rem;"
    )


def neutral_chip_style(*, font_size: str = "0.80rem") -> str:
    """Neutral chip style token used in non-semantic labels (owner/age/count)."""
    return (
        "color:var(--bbva-text-muted); border:1px solid var(--bbva-border-strong); "
        "background:color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2)); "
        f"border-radius:999px; padding:2px 10px; font-weight:700; font-size:{font_size};"
    )
