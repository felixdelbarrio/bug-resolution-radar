"""Bounded, local-only telemetry for performance diagnostics and Codex exports."""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from bug_resolution_radar.config import config_home

SCHEMA_VERSION = "1.0"
DEFAULT_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 90
MAX_EVENTS = 5_000
MAX_FILE_BYTES = 2 * 1024 * 1024
_ALLOWED_DETAIL_KEYS = {
    "metric",
    "navigationType",
    "count",
    "totalMs",
    "maxMs",
    "resourceType",
}


def telemetry_path() -> Path:
    override = str(os.getenv("BUG_RESOLUTION_RADAR_TELEMETRY_PATH", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (config_home() / "data" / "telemetry" / "events.jsonl").resolve()


def _application_version() -> str:
    try:
        return version("bug-resolution-radar")
    except PackageNotFoundError:
        return "development"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime | None = None) -> str:
    return (value or _utc_now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any, *, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _clean_number(value: Any, *, minimum: float = 0.0, maximum: float = 3_600_000.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return minimum
    return round(min(max(number, minimum), maximum), 2)


def _safe_details(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _ALLOWED_DETAIL_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = _clean_number(value)
        elif isinstance(value, str):
            out[key] = _clean_text(value, limit=60)
    return out


def _safe_route(value: Any) -> str:
    raw = _clean_text(value, limit=160).split("?", 1)[0]
    segments = raw.split("/")
    for index, segment in enumerate(segments):
        previous = segments[index - 1].lower() if index > 0 else ""
        if previous in {"notes", "entries"} or re.fullmatch(
            r"(?:[A-Z]{2,10}-\d+|INC\d+|[0-9a-f]{8,}|[0-9a-f-]{32,})",
            segment,
            flags=re.IGNORECASE,
        ):
            segments[index] = ":id"
    return "/".join(segments)


def sanitize_event(raw: dict[str, Any], *, layer: str | None = None) -> dict[str, Any]:
    """Return the strict, non-business-data telemetry contract."""
    clean_layer = _clean_text(layer or raw.get("layer"), limit=16).lower()
    if clean_layer not in {"backend", "frontend"}:
        clean_layer = "frontend"
    status = _clean_text(raw.get("status"), limit=16).lower()
    if status not in {"success", "error"}:
        status = "success"
    event: dict[str, Any] = {
        "timestamp": _iso_utc(),
        "layer": clean_layer,
        "name": _clean_text(raw.get("name"), limit=80) or "unknown",
        "status": status,
        "durationMs": _clean_number(raw.get("durationMs")),
    }
    route = _safe_route(raw.get("route"))
    if route:
        event["route"] = route
    method = _clean_text(raw.get("method"), limit=10).upper()
    if method:
        event["method"] = method
    try:
        status_code = int(raw.get("statusCode") or 0)
    except (TypeError, ValueError):
        status_code = 0
    if 100 <= status_code <= 599:
        event["statusCode"] = status_code
    details = _safe_details(raw.get("details"))
    if details:
        event["details"] = details
    return event


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return round(ordered[index], 2)


class TelemetryStore:
    """Append-only JSONL store with infrequent bounded compaction."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or telemetry_path()).expanduser().resolve()
        self._lock = Lock()

    def append(self, event: dict[str, Any]) -> None:
        self.append_many([event])

    def append_many(self, events: Iterable[dict[str, Any]]) -> int:
        clean = [sanitize_event(event) for event in events]
        if not clean:
            return 0
        lines = "".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in clean)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(lines)
            if self.path.stat().st_size > MAX_FILE_BYTES:
                self._compact_locked()
        return len(clean)

    def _read_locked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(value, dict):
                    out.append(value)
        return out[-MAX_EVENTS:]

    def _compact_locked(self) -> None:
        cutoff = _utc_now() - timedelta(days=MAX_RETENTION_DAYS)
        retained = [
            event
            for event in self._read_locked()
            if (_parse_timestamp(event.get("timestamp")) or cutoff) >= cutoff
        ][-MAX_EVENTS:]
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            for event in retained:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        temp.replace(self.path)

    def events(self, *, days: int = DEFAULT_RETENTION_DAYS) -> list[dict[str, Any]]:
        safe_days = min(MAX_RETENTION_DAYS, max(1, int(days)))
        cutoff = _utc_now() - timedelta(days=safe_days)
        with self._lock:
            rows = self._read_locked()
        return [
            row
            for row in rows
            if (_parse_timestamp(row.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
        ]

    def summary(self, *, days: int = DEFAULT_RETENTION_DAYS) -> dict[str, Any]:
        rows = self.events(days=days)
        durations = [float(row.get("durationMs") or 0) for row in rows if float(row.get("durationMs") or 0) > 0]
        by_layer = Counter(str(row.get("layer") or "unknown") for row in rows)
        by_status = Counter(str(row.get("status") or "unknown") for row in rows)
        grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
        counts: Counter[tuple[str, str, str]] = Counter()
        for row in rows:
            key = (
                str(row.get("layer") or "unknown"),
                str(row.get("name") or "unknown"),
                str(row.get("route") or ""),
            )
            counts[key] += 1
            duration = float(row.get("durationMs") or 0)
            if duration > 0:
                grouped[key].append(duration)
        operations = []
        for key, count in counts.most_common(30):
            values = grouped.get(key, [])
            operations.append(
                {
                    "layer": key[0],
                    "name": key[1],
                    "route": key[2],
                    "count": count,
                    "averageDurationMs": round(sum(values) / len(values), 2) if values else 0.0,
                    "p95DurationMs": _percentile(values, 0.95),
                    "errorCount": sum(
                        1
                        for row in rows
                        if str(row.get("layer")) == key[0]
                        and str(row.get("name")) == key[1]
                        and str(row.get("route") or "") == key[2]
                        and row.get("status") == "error"
                    ),
                }
            )
        return {
            "days": min(MAX_RETENTION_DAYS, max(1, int(days))),
            "eventCount": len(rows),
            "errorCount": int(by_status.get("error", 0)),
            "averageDurationMs": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "p95DurationMs": _percentile(durations, 0.95),
            "byLayer": dict(sorted(by_layer.items())),
            "operations": operations,
            "latestTimestamp": str(rows[-1].get("timestamp") or "") if rows else "",
        }

    def export(self, *, days: int = DEFAULT_RETENTION_DAYS) -> dict[str, Any]:
        rows = self.events(days=days)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": _iso_utc(),
            "application": {
                "name": "bug-resolution-radar",
                "version": _application_version(),
                "runtime": {
                    "os": platform.system(),
                    "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                },
            },
            "privacy": {
                "localOnly": True,
                "containsBusinessData": False,
                "excluded": ["issue content", "credentials", "user identity", "absolute paths"],
            },
            "methodology": {
                "retentionDays": min(MAX_RETENTION_DAYS, max(1, int(days))),
                "maximumStoredEvents": MAX_EVENTS,
                "durationStatisticsExcludeZero": True,
                "frontendEventsAreBuffered": True,
            },
            "summary": self.summary(days=days),
            "events": rows,
        }
