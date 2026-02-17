from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


class NotesStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._notes: Dict[str, str] = {}

    def load(self) -> None:
        if self.path.exists():
            self._notes = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._notes = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, key: str) -> Optional[str]:
        return self._notes.get(key)

    def set(self, key: str, note: str) -> None:
        self._notes[key] = note
