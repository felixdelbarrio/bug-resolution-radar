from __future__ import annotations

import json
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
        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return HelixDocument.model_validate(data)

    def save(self, doc: HelixDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(doc.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self._path)
