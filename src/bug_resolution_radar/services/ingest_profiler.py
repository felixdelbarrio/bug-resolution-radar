"""Low-overhead ingestion profiling by phase with JSONL persistence."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..common.utils import now_iso

_PROFILE_WRITE_LOCK = threading.Lock()


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if token in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v or 0.0) for v in values)
    if len(ordered) == 1:
        return float(ordered[0])
    q_clamped = min(1.0, max(0.0, float(q)))
    idx = (len(ordered) - 1) * q_clamped
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(ordered[lo])
    weight = idx - lo
    return float(ordered[lo] * (1.0 - weight) + ordered[hi] * weight)


def _summary(values: List[float]) -> Dict[str, float]:
    cleaned = [float(v or 0.0) for v in values]
    if not cleaned:
        return {
            "count": 0.0,
            "total": 0.0,
            "mean": 0.0,
            "max": 0.0,
            "p50": 0.0,
            "p95": 0.0,
        }
    total = float(sum(cleaned))
    count = float(len(cleaned))
    return {
        "count": count,
        "total": total,
        "mean": total / count if count > 0 else 0.0,
        "max": max(cleaned),
        "p50": _percentile(cleaned, 0.50),
        "p95": _percentile(cleaned, 0.95),
    }


def _rss_kib() -> float:
    # ru_maxrss units differ by platform:
    # - Linux: KiB
    # - macOS: bytes
    try:
        import resource

        raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0.0)
    except Exception:
        return 0.0
    if os.name == "posix" and "darwin" in str(os.uname().sysname).lower():
        return raw / 1024.0
    return raw


def _phase_key(phase: str, source_id: str) -> str:
    return f"{str(phase or '').strip()}::{str(source_id or '').strip()}"


@dataclass(frozen=True)
class PhaseSample:
    phase: str
    source_id: str
    source_label: str
    attempt: int
    elapsed_ms: float
    cpu_ms: float
    rss_delta_kib: float


class IngestRunProfiler:
    """Collect per-phase measurements and emit persisted run summaries."""

    def __init__(
        self,
        *,
        connector: str,
        run_id: int,
        enabled: Optional[bool] = None,
        output_path: Optional[str] = None,
    ) -> None:
        default_enabled = _coerce_bool(os.getenv("INGEST_PROFILE_ENABLED"), default=True)
        self.enabled = default_enabled if enabled is None else bool(enabled)
        self.connector = str(connector or "").strip().lower()
        self.run_id = int(run_id or 0)
        self.output_path = str(output_path or "").strip() or str(
            os.getenv("INGEST_PROFILE_JSONL_PATH", "data/observability/ingest_profiles.jsonl")
        )
        self._samples: List[PhaseSample] = []
        self._counters: Dict[str, int] = {}
        self._run_started_at = now_iso()
        self._run_start_wall = time.perf_counter()
        self._run_start_cpu = time.process_time()

    class _PhaseScope:
        def __init__(
            self,
            profiler: "IngestRunProfiler",
            *,
            phase: str,
            source_id: str,
            source_label: str,
            attempt: int,
        ) -> None:
            self._profiler = profiler
            self._phase = str(phase or "").strip() or "unknown"
            self._source_id = str(source_id or "").strip()
            self._source_label = str(source_label or "").strip()
            self._attempt = max(1, int(attempt or 1))
            self._start_wall = 0.0
            self._start_cpu = 0.0
            self._start_rss = 0.0

        def __enter__(self) -> None:
            if not self._profiler.enabled:
                return None
            self._start_wall = time.perf_counter()
            self._start_cpu = time.process_time()
            self._start_rss = _rss_kib()
            return None

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            if not self._profiler.enabled:
                return None
            elapsed_ms = max(0.0, (time.perf_counter() - self._start_wall) * 1000.0)
            cpu_ms = max(0.0, (time.process_time() - self._start_cpu) * 1000.0)
            rss_delta_kib = max(0.0, _rss_kib() - self._start_rss)
            self._profiler._samples.append(
                PhaseSample(
                    phase=self._phase,
                    source_id=self._source_id,
                    source_label=self._source_label,
                    attempt=self._attempt,
                    elapsed_ms=elapsed_ms,
                    cpu_ms=cpu_ms,
                    rss_delta_kib=rss_delta_kib,
                )
            )
            return None

    def phase(
        self,
        *,
        phase: str,
        source_id: str = "",
        source_label: str = "",
        attempt: int = 1,
    ) -> "_PhaseScope":
        return self._PhaseScope(
            self,
            phase=phase,
            source_id=source_id,
            source_label=source_label,
            attempt=attempt,
        )

    def increment(self, counter_name: str, delta: int = 1) -> None:
        name = str(counter_name or "").strip()
        if not name:
            return
        self._counters[name] = int(self._counters.get(name, 0) or 0) + int(delta or 0)

    def _phase_stats(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        buckets: Dict[str, List[PhaseSample]] = {}
        for sample in self._samples:
            phase = str(sample.phase or "").strip() or "unknown"
            buckets.setdefault(phase, []).append(sample)

        out: Dict[str, Dict[str, Dict[str, float]]] = {}
        for phase_name, samples in buckets.items():
            out[phase_name] = {
                "elapsed_ms": _summary([s.elapsed_ms for s in samples]),
                "cpu_ms": _summary([s.cpu_ms for s in samples]),
                "rss_delta_kib": _summary([s.rss_delta_kib for s in samples]),
            }
        return out

    def _source_stats(self) -> Dict[str, Dict[str, float]]:
        totals: Dict[str, Dict[str, float]] = {}
        for sample in self._samples:
            key = _phase_key(sample.phase, sample.source_id)
            item = totals.setdefault(
                key,
                {
                    "elapsed_ms_total": 0.0,
                    "cpu_ms_total": 0.0,
                    "rss_delta_kib_total": 0.0,
                    "samples": 0.0,
                },
            )
            item["elapsed_ms_total"] += float(sample.elapsed_ms or 0.0)
            item["cpu_ms_total"] += float(sample.cpu_ms or 0.0)
            item["rss_delta_kib_total"] += float(sample.rss_delta_kib or 0.0)
            item["samples"] += 1.0
        return totals

    def build_record(
        self,
        *,
        state: str,
        summary: str,
        total_sources: int,
        success_count: int,
    ) -> Dict[str, Any]:
        run_elapsed_ms = max(0.0, (time.perf_counter() - self._run_start_wall) * 1000.0)
        run_cpu_ms = max(0.0, (time.process_time() - self._run_start_cpu) * 1000.0)
        return {
            "schema_version": "1.0",
            "connector": self.connector,
            "run_id": self.run_id,
            "state": str(state or "unknown").strip().lower(),
            "summary": str(summary or "").strip(),
            "started_at": self._run_started_at,
            "finished_at": now_iso(),
            "total_sources": int(total_sources or 0),
            "success_count": int(success_count or 0),
            "run_elapsed_ms": run_elapsed_ms,
            "run_cpu_ms": run_cpu_ms,
            "phase_stats": self._phase_stats(),
            "source_phase_totals": self._source_stats(),
            "counters": {k: int(v or 0) for k, v in self._counters.items()},
            "sample_count": len(self._samples),
        }

    def persist(self, record: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        path = Path(self.output_path)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with _PROFILE_WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
