"""Local notes persistence model and storage helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4


@dataclass(frozen=True)
class NoteEntry:
    id: str
    created_at: str
    note: str

    def to_payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "createdAt": self.created_at,
            "dateLabel": format_entry_date(self.created_at),
            "note": self.note,
        }


def _clean_note(value: object) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _new_entry_id(created_at: str) -> str:
    compact = "".join(ch for ch in str(created_at or "") if ch.isalnum())
    return f"{compact[:20] or 'note'}-{uuid4().hex[:8]}"


def _parse_entry_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_entry_date(value: object) -> str:
    parsed = _parse_entry_datetime(value)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    raw = str(value or "").strip()
    return raw or "Sin fecha"


def format_note_log(entries: list[NoteEntry]) -> str:
    blocks: list[str] = []
    for entry in entries:
        note = _clean_note(entry.note)
        if not note:
            continue
        blocks.append(f"{format_entry_date(entry.created_at)}:\n{note}")
    return "\n\n".join(blocks).strip()


class NotesStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._notes: Dict[str, list[NoteEntry]] = {}

    def _coerce_entry(self, raw: object, *, index: int) -> NoteEntry | None:
        if isinstance(raw, dict):
            note = _clean_note(raw.get("note"))
            if not note:
                return None
            created_at = str(raw.get("createdAt") or raw.get("created_at") or "").strip()
            entry_id = str(raw.get("id") or "").strip()
            if not entry_id:
                entry_id = _new_entry_id(created_at or f"legacy-{index}")
            return NoteEntry(id=entry_id, created_at=created_at, note=note)
        note = _clean_note(raw)
        if not note:
            return None
        return NoteEntry(id=f"legacy-{index}", created_at="", note=note)

    def _coerce_entries(self, raw: object) -> list[NoteEntry]:
        candidate_entries: list[object]
        if isinstance(raw, dict):
            entries_raw = raw.get("entries")
            if isinstance(entries_raw, list):
                candidate_entries = entries_raw
            elif "note" in raw:
                candidate_entries = [raw]
            else:
                candidate_entries = []
        elif isinstance(raw, list):
            candidate_entries = raw
        else:
            candidate_entries = [raw]

        entries: list[NoteEntry] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(candidate_entries):
            entry = self._coerce_entry(item, index=index)
            if entry is None:
                continue
            entry_id = entry.id
            if entry_id in seen_ids:
                entry_id = _new_entry_id(entry.created_at or f"legacy-{index}")
                entry = NoteEntry(id=entry_id, created_at=entry.created_at, note=entry.note)
            seen_ids.add(entry_id)
            entries.append(entry)
        return entries

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._notes = {}
                return
            if isinstance(raw, dict):
                notes: Dict[str, list[NoteEntry]] = {}
                for key, value in raw.items():
                    clean_key = str(key or "").strip().upper()
                    if not clean_key:
                        continue
                    entries = self._coerce_entries(value)
                    if entries:
                        notes[clean_key] = entries
                self._notes = notes
            else:
                self._notes = {}
        else:
            self._notes = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            key: {
                "entries": [
                    {
                        "id": entry.id,
                        "createdAt": entry.created_at,
                        "note": entry.note,
                    }
                    for entry in entries
                    if _clean_note(entry.note)
                ]
            }
            for key, entries in sorted(self._notes.items(), key=lambda item: item[0])
            if entries
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, key: str) -> Optional[str]:
        entries = self.get_entries(key)
        if not entries:
            return None
        return format_note_log(entries)

    def get_entries(self, key: str) -> list[NoteEntry]:
        return list(self._notes.get(str(key or "").strip().upper(), ()))

    def latest_created_at(self, key: str) -> str:
        entries = self.get_entries(key)
        for entry in reversed(entries):
            if str(entry.created_at or "").strip():
                return entry.created_at
        return ""

    def append(self, key: str, note: str) -> Optional[NoteEntry]:
        clean_key = str(key or "").strip().upper()
        clean_note = _clean_note(note)
        if not clean_key:
            return None
        if not clean_note:
            self.delete(clean_key)
            return None
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        entry = NoteEntry(id=_new_entry_id(created_at), created_at=created_at, note=clean_note)
        self._notes.setdefault(clean_key, []).append(entry)
        return entry

    def set(self, key: str, note: str) -> None:
        clean_key = str(key or "").strip().upper()
        clean_note = _clean_note(note)
        if not clean_key:
            return
        if not clean_note:
            self.delete(clean_key)
            return
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self._notes[clean_key] = [
            NoteEntry(id=_new_entry_id(created_at), created_at=created_at, note=clean_note)
        ]

    def delete(self, key: str) -> None:
        clean_key = str(key or "").strip().upper()
        if not clean_key:
            return
        self._notes.pop(clean_key, None)

    def delete_entry(self, key: str, entry_id: str) -> bool:
        clean_key = str(key or "").strip().upper()
        clean_entry_id = str(entry_id or "").strip()
        if not clean_key or not clean_entry_id:
            return False
        entries = self._notes.get(clean_key, [])
        kept = [entry for entry in entries if entry.id != clean_entry_id]
        removed = len(kept) != len(entries)
        if not kept:
            self._notes.pop(clean_key, None)
        else:
            self._notes[clean_key] = kept
        return removed

    def items(self) -> list[tuple[str, str]]:
        return [
            (key, format_note_log(entries))
            for key, entries in sorted(self._notes.items(), key=lambda item: item[0])
            if entries
        ]

    def entry_items(self) -> list[tuple[str, list[NoteEntry]]]:
        return sorted(
            ((key, list(entries)) for key, entries in self._notes.items() if entries),
            key=lambda item: item[0],
        )


def note_entries_payload(entries: list[NoteEntry]) -> list[dict[str, str]]:
    return [entry.to_payload() for entry in entries if _clean_note(entry.note)]
