"""Persistent storage for cross-session insights learning state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from bug_resolution_radar.common.utils import now_iso
from bug_resolution_radar.config import Settings


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def learning_scope_key(country: str, source_id: str) -> str:
    country_token = str(country or "").strip() or "global"
    source_token = str(source_id or "").strip() or "all-sources"
    return f"{country_token}::{source_token}"


def default_learning_path(settings: Settings) -> Path:
    raw = str(getattr(settings, "INSIGHTS_LEARNING_PATH", "") or "").strip()
    if raw:
        return Path(raw)
    return Path("data/insights_learning.json")


class InsightsLearningStore:
    """Local JSON store with per-scope learning state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._raw: Dict[str, Any] = {"version": 3, "scopes": {}}

    def load(self) -> None:
        if not self.path.exists():
            self._raw = {"version": 3, "scopes": {}}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._raw = {"version": 3, "scopes": {}}
            return
        if not isinstance(data, dict) or data.get("version") != 3:
            self._raw = {"version": 3, "scopes": {}}
            return
        scopes = data.get("scopes")
        if not isinstance(scopes, dict):
            scopes = {}
        self._raw = {"version": 3, "scopes": scopes}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def record_snapshot(
        self,
        scope: str,
        *,
        snapshot: Dict[str, Any],
        country: str,
        source_id: str,
    ) -> Tuple[Dict[str, Any], bool]:
        """Persist a distinct KPI measurement and return the previous one."""
        current_snapshot = _as_dict(snapshot)
        scopes = _as_dict(self._raw.get("scopes"))
        record = _as_dict(scopes.get(scope))
        measurements = [
            _as_dict(item) for item in list(record.get("measurements") or []) if _as_dict(item)
        ]
        latest = measurements[-1] if measurements else {}
        previous = measurements[-2] if len(measurements) > 1 else {}
        current_hash = json.dumps(current_snapshot, ensure_ascii=False, sort_keys=True)
        latest_hash = json.dumps(latest, ensure_ascii=False, sort_keys=True)
        if latest and current_hash == latest_hash:
            return previous, False

        measurements.append(current_snapshot)
        scopes[scope] = {
            "country": str(country or ""),
            "source_id": str(source_id or ""),
            "measurements": measurements[-30:],
            "updated_at": now_iso(),
        }
        self._raw["scopes"] = scopes
        self._raw["version"] = 3
        return latest, True

    def remove_source(self, source_id: str) -> int:
        sid = str(source_id or "").strip()
        if not sid:
            return 0

        scopes = _as_dict(self._raw.get("scopes"))
        kept: Dict[str, Any] = {}
        removed = 0
        suffix = f"::{sid}"

        for scope_key, record in scopes.items():
            record_dict = _as_dict(record)
            rec_source_id = str(record_dict.get("source_id") or "").strip()
            scope_txt = str(scope_key or "")
            if rec_source_id == sid or (not rec_source_id and scope_txt.endswith(suffix)):
                removed += 1
                continue
            kept[scope_txt] = record_dict

        if removed > 0:
            self._raw["scopes"] = kept
            self._raw["version"] = 3

        return removed

    def count_source_scopes(self, source_id: str) -> int:
        sid = str(source_id or "").strip()
        if not sid:
            return 0

        scopes = _as_dict(self._raw.get("scopes"))
        suffix = f"::{sid}"
        count = 0
        for scope_key, record in scopes.items():
            record_dict = _as_dict(record)
            rec_source_id = str(record_dict.get("source_id") or "").strip()
            scope_txt = str(scope_key or "")
            if rec_source_id == sid or (not rec_source_id and scope_txt.endswith(suffix)):
                count += 1
        return count

    def count_all_scopes(self) -> int:
        scopes = _as_dict(self._raw.get("scopes"))
        return len(scopes)

    def clear_all(self) -> int:
        scopes = _as_dict(self._raw.get("scopes"))
        removed = len(scopes)
        self._raw = {"version": 3, "scopes": {}}
        return removed
