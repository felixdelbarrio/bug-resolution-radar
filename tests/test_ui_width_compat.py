from __future__ import annotations

from pathlib import Path


def test_streamlit_widgets_do_not_use_content_width_literal() -> None:
    root = Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []
    for py_file in root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if 'width="content"' in text or "width='content'" in text:
            offenders.append(str(py_file))
    assert offenders == []
