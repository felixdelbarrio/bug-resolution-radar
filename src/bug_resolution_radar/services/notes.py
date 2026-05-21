"""Local notes persistence model and storage helpers."""

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
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._notes = {}
                return
            if isinstance(raw, dict):
                self._notes = {
                    str(key).strip().upper(): str(value or "").strip()
                    for key, value in raw.items()
                    if str(key).strip() and str(value or "").strip()
                }
            else:
                self._notes = {}
        else:
            self._notes = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, key: str) -> Optional[str]:
        return self._notes.get(str(key or "").strip().upper())

    def set(self, key: str, note: str) -> None:
        clean_key = str(key or "").strip().upper()
        clean_note = str(note or "").strip()
        if not clean_key:
            return
        if not clean_note:
            self.delete(clean_key)
            return
        self._notes[clean_key] = clean_note

    def delete(self, key: str) -> None:
        clean_key = str(key or "").strip().upper()
        if not clean_key:
            return
        self._notes.pop(clean_key, None)

    def items(self) -> list[tuple[str, str]]:
        return sorted(self._notes.items(), key=lambda item: item[0])
