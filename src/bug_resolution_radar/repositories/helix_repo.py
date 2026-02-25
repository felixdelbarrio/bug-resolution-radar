"""Repository access layer for Helix endpoints and query payloads."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from bug_resolution_radar.schema_helix import HelixDocument


class HelixRepo:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Optional[HelixDocument]:
        if not self._path.exists():
            return None
        return HelixDocument.model_validate_json(self._path.read_text(encoding="utf-8"))

    def save(self, doc: HelixDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = doc.model_dump_json(ensure_ascii=False)
        with tmp.open("w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self._path)
