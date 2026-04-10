from __future__ import annotations

import ast
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "bug_resolution_radar"


def _python_files() -> list[Path]:
    return [path for path in SRC_ROOT.rglob("*.py") if "__pycache__" not in path.parts]


def _is_ui_path(path: Path) -> bool:
    return "ui" in path.relative_to(SRC_ROOT).parts


def test_backend_modules_do_not_import_ui_or_streamlit() -> None:
    offenders: list[str] = []

    for path in _python_files():
        if _is_ui_path(path):
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = str(alias.name or "")
                    if name == "streamlit" or name.startswith("bug_resolution_radar.ui"):
                        offenders.append(f"{path.relative_to(SRC_ROOT)} -> {name}")
            elif isinstance(node, ast.ImportFrom):
                module = str(node.module or "")
                if module == "streamlit" or module.startswith("bug_resolution_radar.ui"):
                    offenders.append(f"{path.relative_to(SRC_ROOT)} -> {module}")

    assert offenders == [], "Unexpected backend imports:\n" + "\n".join(sorted(offenders))
