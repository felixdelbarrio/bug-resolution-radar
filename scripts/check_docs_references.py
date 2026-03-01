#!/usr/bin/env python3
"""Validate documentation integrity and local path references."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

REQUIRED_DOC_FILES: Tuple[str, ...] = (
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/INSIGHTS_ENGINE.md",
    "docs/THEMING.md",
    "docs/QUALITY.md",
    "docs/CODEBASE.md",
)

REQUIRED_HEADINGS: Dict[str, Tuple[str, ...]] = {
    "README.md": ("## Quick Start", "## Architecture", "## Quality"),
    "docs/ARCHITECTURE.md": ("## Runtime Flow", "## Module Layers"),
    "docs/INSIGHTS_ENGINE.md": ("## Pipeline", "## Extension Points"),
    "docs/THEMING.md": ("## Theme Tokens", "## Plotly Rules"),
    "docs/QUALITY.md": ("## Local Commands", "## CI Pipeline"),
    "docs/CODEBASE.md": ("## Core Package Map", "## UI Package Map"),
}

STALE_DOC_TOKENS: Tuple[str, ...] = (
    "src/bug_resolution_radar/kpis.py",
    "src/bug_resolution_radar/insights.py",
    "src/bug_resolution_radar/security.py",
    "src/bug_resolution_radar/ui/dashboard/overview.py",
    "src/bug_resolution_radar/ui/dashboard/trends.py",
    "JIRA_JQL",
    "ANALYSIS_LOOKBACK_DAYS",
)

CODE_BLOCK_PATH_RE = re.compile(
    r"`((?:src|tests|scripts|docs|\.github/workflows|assets)/[^`]+|README\.md|Makefile|pyproject\.toml|run_streamlit\.py|app\.py)`"
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
LOCAL_FILE_RE = re.compile(r"^(?:src|tests|scripts|docs|\.github/workflows|assets)/")


def _normalize_local_path(token: str) -> str:
    txt = str(token or "").strip()
    if not txt:
        return ""
    txt = txt.split("#", 1)[0].strip()
    txt = txt.rstrip(".,;:")
    # Strip optional :line or :line:column suffixes.
    m = re.match(r"^(.+?):\d+(?::\d+)?$", txt)
    if m:
        txt = m.group(1).strip()
    return txt


def _collect_reference_errors(*, repo_root: Path, rel_path: str, text: str) -> List[str]:
    errors: List[str] = []
    seen: set[str] = set()

    for m in CODE_BLOCK_PATH_RE.finditer(text):
        raw = _normalize_local_path(m.group(1))
        if not raw or raw in seen:
            continue
        seen.add(raw)
        target = (repo_root / raw).resolve()
        if not target.exists():
            errors.append(f"{rel_path}: referencia inexistente `{raw}`")

    for m in MARKDOWN_LINK_RE.finditer(text):
        target_raw = str(m.group(1) or "").strip()
        if not target_raw:
            continue
        if "://" in target_raw or target_raw.startswith("#"):
            continue
        normalized = _normalize_local_path(target_raw)
        if not normalized or not LOCAL_FILE_RE.match(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        target = (repo_root / normalized).resolve()
        if not target.exists():
            errors.append(f"{rel_path}: link local inexistente `{normalized}`")

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors: List[str] = []

    for rel in REQUIRED_DOC_FILES:
        path = repo_root / rel
        if not path.exists():
            errors.append(f"Falta documentación requerida: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for heading in REQUIRED_HEADINGS.get(rel, ()):
            if heading not in text:
                errors.append(f"{rel}: falta heading requerido `{heading}`")
        errors.extend(_collect_reference_errors(repo_root=repo_root, rel_path=rel, text=text))

    docs_scope = [repo_root / "README.md", *sorted((repo_root / "docs").glob("*.md"))]
    for path in docs_scope:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(repo_root))
        for token in STALE_DOC_TOKENS:
            if token in text:
                errors.append(f"{rel}: referencia obsoleta detectada `{token}`")

    if errors:
        print("Documentación inválida:")
        for err in sorted(set(errors)):
            print(f"- {err}")
        return 1

    print("Documentación validada correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
