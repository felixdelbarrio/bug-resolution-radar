"""Reusable BBVA corporate lockup for every generated presentation."""

from __future__ import annotations

from typing import Any

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import MSO_VERTICAL_ANCHOR
from pptx.util import Inches, Pt

from bug_resolution_radar.theme.brand_identity import (
    CORPORATE_DESCRIPTOR_LINES,
    CORPORATE_WORDMARK,
)
from bug_resolution_radar.theme.design_tokens import (
    BBVA_ELECTRIC,
    BBVA_FONT_SANS_MEDIUM_PPT,
    BBVA_MIDNIGHT,
    BBVA_SERENE,
    BBVA_WHITE,
    hex_to_rgb,
)

_LOCKUP_PREFIX = "BBVA Corporate Lockup"


def _rgb(color: str) -> RGBColor:
    return RGBColor(*hex_to_rgb(color))


def _fill_rgb(fill: Any) -> tuple[int, int, int] | None:
    try:
        rgb = fill.fore_color.rgb
        if rgb is None:
            return None
        return int(rgb[0]), int(rgb[1]), int(rgb[2])
    except Exception:
        return None


def _slide_is_dark(slide: Any, *, slide_width: int, slide_height: int) -> bool:
    for shape in slide.shapes:
        if int(getattr(shape, "width", 0) or 0) < int(slide_width * 0.9):
            continue
        if int(getattr(shape, "height", 0) or 0) < int(slide_height * 0.9):
            continue
        rgb = _fill_rgb(getattr(shape, "fill", None))
        if rgb is not None:
            return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) < 125
    rgb = _fill_rgb(getattr(getattr(slide, "background", None), "fill", None))
    return bool(
        rgb is not None
        and (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) < 125
    )


def add_corporate_lockup(
    slide: Any,
    *,
    slide_width: int,
    slide_height: int,
) -> None:
    """Add the canonical lockup to the reserved footer area of one slide."""
    if any(str(getattr(shape, "name", "")).startswith(_LOCKUP_PREFIX) for shape in slide.shapes):
        return

    width_in = float(slide_width) / 914_400
    height_in = float(slide_height) / 914_400
    lockup_width = min(2.45, max(2.05, width_in * 0.22))
    lockup_height = 0.25
    left = width_in - lockup_width - 0.28
    top = height_in - lockup_height - 0.06
    wordmark_width = 0.58
    divider_x = left + wordmark_width + 0.08
    descriptor_x = divider_x + 0.10
    descriptor_width = lockup_width - (descriptor_x - left)
    dark = _slide_is_dark(slide, slide_width=slide_width, slide_height=slide_height)
    wordmark_color = BBVA_WHITE if dark else BBVA_ELECTRIC
    descriptor_color = BBVA_SERENE if dark else BBVA_MIDNIGHT

    wordmark = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(wordmark_width), Inches(lockup_height)
    )
    wordmark.name = f"{_LOCKUP_PREFIX} Wordmark"
    wordmark.text_frame.clear()
    wordmark.text_frame.margin_left = 0
    wordmark.text_frame.margin_right = 0
    wordmark.text_frame.margin_top = 0
    wordmark.text_frame.margin_bottom = 0
    wordmark.text_frame.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    run = wordmark.text_frame.paragraphs[0].add_run()
    run.text = CORPORATE_WORDMARK
    run.font.name = BBVA_FONT_SANS_MEDIUM_PPT
    run.font.bold = True
    run.font.size = Pt(9.5)
    run.font.color.rgb = _rgb(wordmark_color)

    divider = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        Inches(divider_x),
        Inches(top + 0.025),
        Inches(0.012),
        Inches(lockup_height - 0.05),
    )
    divider.name = f"{_LOCKUP_PREFIX} Divider"
    divider.fill.solid()
    divider.fill.fore_color.rgb = _rgb(descriptor_color)
    divider.line.fill.background()

    descriptor = slide.shapes.add_textbox(
        Inches(descriptor_x),
        Inches(top),
        Inches(descriptor_width),
        Inches(lockup_height),
    )
    descriptor.name = f"{_LOCKUP_PREFIX} Descriptor"
    descriptor.text_frame.clear()
    descriptor.text_frame.margin_left = 0
    descriptor.text_frame.margin_right = 0
    descriptor.text_frame.margin_top = 0
    descriptor.text_frame.margin_bottom = 0
    descriptor.text_frame.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    descriptor_run = descriptor.text_frame.paragraphs[0].add_run()
    descriptor_run.text = "\n".join(CORPORATE_DESCRIPTOR_LINES)
    descriptor_run.font.name = BBVA_FONT_SANS_MEDIUM_PPT
    descriptor_run.font.size = Pt(5.0)
    descriptor_run.font.color.rgb = _rgb(descriptor_color)


def add_corporate_lockup_to_all_slides(presentation: Any) -> None:
    for slide in presentation.slides:
        add_corporate_lockup(
            slide,
            slide_width=int(presentation.slide_width),
            slide_height=int(presentation.slide_height),
        )
