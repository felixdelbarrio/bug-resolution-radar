from __future__ import annotations

"""
Streamlit entrypoint.

This repository uses a "src/" layout, so we ensure "src" is on sys.path
when running via: streamlit run app.py
"""

import sys
from pathlib import Path

# Add <repo>/src to PYTHONPATH for Streamlit + local execution
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bug_resolution_radar.ui.app import main  # noqa: E402


if __name__ == "__main__":
    main()