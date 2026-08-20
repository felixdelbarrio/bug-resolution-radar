from __future__ import annotations

import re
from pathlib import Path

from bug_resolution_radar.theme.design_tokens import (
    BBVA_BLACK,
    BBVA_BLUE_LIGHT,
    BBVA_CONTENT_MAX_PX,
    BBVA_ELECTRIC,
    BBVA_GREY_200,
    BBVA_GREY_300,
    BBVA_GREY_400,
    BBVA_GREY_500,
    BBVA_GREY_600,
    BBVA_GREY_700,
    BBVA_GREY_800,
    BBVA_GREY_900,
    BBVA_GRID_BASE_PX,
    BBVA_GRID_GUTTER_PX,
    BBVA_GRID_MARGIN_PX,
    BBVA_MIDNIGHT,
    BBVA_RADIUS_INNER_PX,
    BBVA_RADIUS_OUTER_PX,
    BBVA_ROYAL,
    BBVA_ROYAL_DARK,
    BBVA_SERENE,
    BBVA_SERENE_DARK,
    BBVA_WHITE,
    frontend_theme_tokens,
)

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def _frontend_file(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def _type_block(source: str, type_name: str) -> str:
    start = source.index(f"export type {type_name}")
    next_type = source.find("\nexport type ", start + 1)
    return source[start:] if next_type == -1 else source[start:next_type]


def _contrast_ratio(first: str, second: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_bbva_experience_palette_and_layout_are_canonical() -> None:
    palette = {
        "midnight": BBVA_MIDNIGHT,
        "electric": BBVA_ELECTRIC,
        "royalDark": BBVA_ROYAL_DARK,
        "royal": BBVA_ROYAL,
        "sereneDark": BBVA_SERENE_DARK,
        "serene": BBVA_SERENE,
        "blueLight": BBVA_BLUE_LIGHT,
        "black": BBVA_BLACK,
        "grey900": BBVA_GREY_900,
        "grey800": BBVA_GREY_800,
        "grey700": BBVA_GREY_700,
        "grey600": BBVA_GREY_600,
        "grey500": BBVA_GREY_500,
        "grey400": BBVA_GREY_400,
        "grey300": BBVA_GREY_300,
        "grey200": BBVA_GREY_200,
        "white": BBVA_WHITE,
    }
    assert palette == {
        "midnight": "#070E46",
        "electric": "#001391",
        "royalDark": "#2165CA",
        "royal": "#0C6DFF",
        "sereneDark": "#53A9EF",
        "serene": "#85C8FF",
        "blueLight": "#D6E9F8",
        "black": "#000519",
        "grey900": "#11192D",
        "grey800": "#222C42",
        "grey700": "#334056",
        "grey600": "#46536D",
        "grey500": "#ADB8C2",
        "grey400": "#CAD1D8",
        "grey300": "#E2E6EA",
        "grey200": "#F7F8F8",
        "white": "#FFFFFF",
    }
    assert (
        BBVA_GRID_BASE_PX,
        BBVA_GRID_MARGIN_PX,
        BBVA_GRID_GUTTER_PX,
        BBVA_CONTENT_MAX_PX,
    ) == (8, 24, 24, 1296)
    assert (BBVA_RADIUS_OUTER_PX, BBVA_RADIUS_INNER_PX) == (16, 8)


def test_frontend_runtime_theme_exposes_the_same_design_contract() -> None:
    tokens = frontend_theme_tokens()
    light = tokens["light"]
    dark = tokens["dark"]

    expected_light = {
        "--bbva-midnight": BBVA_MIDNIGHT,
        "--bbva-electric": BBVA_ELECTRIC,
        "--bbva-royal-dark": BBVA_ROYAL_DARK,
        "--bbva-royal": BBVA_ROYAL,
        "--bbva-serene-dark": BBVA_SERENE_DARK,
        "--bbva-serene": BBVA_SERENE,
        "--bbva-blue-light": BBVA_BLUE_LIGHT,
        "--bbva-black": BBVA_BLACK,
        "--bbva-grey-900": BBVA_GREY_900,
        "--bbva-grey-800": BBVA_GREY_800,
        "--bbva-grey-700": BBVA_GREY_700,
        "--bbva-grey-600": BBVA_GREY_600,
        "--bbva-grey-500": BBVA_GREY_500,
        "--bbva-grey-400": BBVA_GREY_400,
        "--bbva-grey-300": BBVA_GREY_300,
        "--bbva-grey-200": BBVA_GREY_200,
        "--bbva-white": BBVA_WHITE,
    }
    for token_name, value in expected_light.items():
        assert light[token_name] == value

    expected_layout = {
        "--bbva-radius-container": "16px",
        "--bbva-radius-component": "8px",
        "--bbva-grid-base": "8px",
        "--bbva-grid-margin": "24px",
        "--bbva-grid-gutter": "24px",
        "--bbva-content-max": "1296px",
    }
    for mode in (light, dark):
        for token_name, value in expected_layout.items():
            assert mode[token_name] == value
        for token_name, value in expected_light.items():
            assert mode[token_name] == value

    assert light["--bbva-neutral"] == BBVA_GREY_300
    assert dark["--bbva-neutral"] == BBVA_GREY_600
    assert dark["--bbva-surface-2"] == BBVA_BLACK
    assert dark["--bbva-surface"] == BBVA_GREY_900
    assert dark["--bbva-surface-elevated"] == BBVA_GREY_800
    assert dark["--bbva-border"] == BBVA_GREY_700
    assert dark["--bbva-border-strong"] == BBVA_GREY_600
    assert dark["--bbva-text"] == BBVA_GREY_200
    assert dark["--bbva-text-muted"] == BBVA_GREY_400
    assert dark["--bbva-brand-midnight"] == BBVA_MIDNIGHT
    assert dark["--bbva-brand-on-hero"] == BBVA_WHITE
    assert _contrast_ratio(dark["--bbva-text"], dark["--bbva-surface"]) >= 7
    assert _contrast_ratio(dark["--bbva-text-muted"], dark["--bbva-surface"]) >= 4.5
    assert _contrast_ratio(dark["--bbva-brand-on-hero"], dark["--bbva-brand-midnight"]) >= 7


def test_desktop_css_uses_bbva_typography_grid_and_radius_contract() -> None:
    styles = _frontend_file("styles/app.css")
    light_root = styles[: styles.index(':root[data-theme="dark"]')]
    dark_root = styles[styles.index(':root[data-theme="dark"]') : styles.index("\n\n* {")]

    for color in (
        "#070e46",
        "#001391",
        "#2165ca",
        "#0c6dff",
        "#53a9ef",
        "#85c8ff",
        "#d6e9f8",
        "#000519",
        "#11192d",
        "#222c42",
        "#334056",
        "#46536d",
        "#adb8c2",
        "#cad1d8",
        "#e2e6ea",
        "#f7f8f8",
        "#ffffff",
    ):
        assert color in light_root.lower()

    assert "font: 400 15px/24px var(--bbva-font-sans);" in styles
    assert re.search(
        r"h1,\s*h2,\s*h3\s*\{\s*font-family: var\(--bbva-font-headline\);",
        styles,
    )
    assert re.search(
        r"h4,\s*h5,\s*h6\s*\{\s*font-family: var\(--bbva-font-sans\);",
        styles,
    )
    assert "--bbva-grid-base: 8px;" in styles
    assert "--bbva-grid-margin: 24px;" in styles
    assert "--bbva-grid-gutter: 24px;" in styles
    assert "--bbva-content-max: 1296px;" in styles
    assert "--bbva-radius-container: 16px;" in styles
    assert "--bbva-radius-component: 8px;" in styles
    for primitive in (
        "--bbva-midnight",
        "--bbva-electric",
        "--bbva-royal-dark",
        "--bbva-royal",
        "--bbva-serene-dark",
        "--bbva-serene",
        "--bbva-blue-light",
        "--bbva-black",
        "--bbva-white",
    ):
        assert f"{primitive}:" not in dark_root
    assert "--bbva-surface: var(--bbva-grey-900);" in dark_root
    assert "--bbva-surface-2: var(--bbva-black);" in dark_root
    assert "--bbva-surface-elevated: var(--bbva-grey-800);" in dark_root
    assert "background: var(--bbva-brand-midnight);" in styles
    assert "color: var(--bbva-brand-on-hero);" in styles
    assert (
        "width: min(100%, calc(var(--bbva-content-max) + 2 * var(--bbva-grid-margin)));" in styles
    )

    allowed_radius_values = {
        "0",
        "50%",
        "999px",
        "inherit",
        "var(--bbva-radius-container)",
        "var(--bbva-radius-component)",
        "var(--bbva-radius-xl)",
        "var(--bbva-radius-lg)",
        "var(--bbva-radius-md)",
        "var(--bbva-radius-sm)",
    }
    radius_values = re.findall(r"border-radius:\s*([^;]+);", styles)
    assert radius_values
    assert set(value.strip() for value in radius_values) <= allowed_radius_values

    for retired_color in (
        "#072146",
        "#004481",
        "#0051f1",
        "#8be1e9",
        "#f4f6f9",
        "#5c6c84",
        "#5bbeff",
        "#8bd8ff",
        "#041428",
        "#08284c",
        "#f6f9fc",
        "#4ade80",
        "#2dcccd",
    ):
        assert retired_color not in styles.lower()


def test_semantic_color_fallbacks_reference_central_css_tokens() -> None:
    source = _frontend_file("lib/semanticColors.ts")

    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)
    assert '"var(--bbva-status-intake)"' in source
    assert '"var(--bbva-priority-highest)"' in source
    assert '"var(--bbva-neutral)"' in source
    assert "color-mix(in srgb" in source
    assert "configureSemanticColors" not in source


def test_desktop_data_transfer_is_export_only_and_uses_v2_contract() -> None:
    ingest = _frontend_file("pages/IngestPage.tsx")
    panel = _frontend_file("components/DataTransferPanel.tsx")
    api = _frontend_file("lib/api.ts")
    styles = _frontend_file("styles/app.css")
    export_contract = _type_block(api, "DataTransferExportPayload")

    for retired_token in (
        '| "import"',
        '"Importar"',
        "onDataImported",
        "DataTransferImportPayload",
        "DataTransferValidationPayload",
        "DataTransferPackagesPayload",
        "/api/data-transfer/import",
        "/api/data-transfer/validate",
        "/api/data-transfer/packages",
    ):
        assert retired_token not in ingest
        assert retired_token not in panel
        assert retired_token not in api

    for retired_selector in (
        ".transfer-file-picker",
        ".transfer-import",
        ".transfer-validation",
        ".transfer-merge",
        ".transfer-operation-import",
    ):
        assert retired_selector not in styles

    assert 'type IngestTab = Connector | "export";' in ingest
    assert "<DataTransferPanel" in ingest
    assert "Incluye la proyección inmutable de la vista activa" in panel
    assert "presentación exacta" in panel
    assert "artefactos incluidos" in panel
    for field in (
        "scopeKey",
        "scopeLabel",
        "country",
        "scopeMode",
        "sourceIds",
        "dataVersion",
        "referenceDate",
        "immutable: true",
        "semanticContract",
        "projectionSha256",
        "reportSha256",
        "reportSlideCount",
    ):
        assert field in export_contract
