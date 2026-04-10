"""Local API entrypoint for development, packaging and desktop runtime."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bug Resolution Radar API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(
        "bug_resolution_radar.api.app:app",
        host=str(args.host),
        port=int(args.port),
        log_level=str(args.log_level).lower(),
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
