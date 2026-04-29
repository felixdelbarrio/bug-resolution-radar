from __future__ import annotations

from pathlib import Path


def test_makefile_no_longer_exposes_run_api_target() -> None:
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    removed_target = "-".join(("run", "api"))

    assert removed_target not in makefile
    assert removed_target not in readme
