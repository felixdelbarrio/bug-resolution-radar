#!/usr/bin/env python3
"""Print latest ingestion profile summary (p50/p95, CPU, RSS deltas) by phase."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _load_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        txt = str(line or "").strip()
        if not txt:
            continue
        try:
            payload = json.loads(txt)
        except Exception:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _fmt_ms(value: Any) -> str:
    try:
        return f"{float(value):.2f}ms"
    except Exception:
        return "0.00ms"


def _fmt_kib(value: Any) -> str:
    try:
        return f"{float(value):.2f} KiB"
    except Exception:
        return "0.00 KiB"


def _iter_phase_rows(record: Dict[str, Any]) -> Iterable[str]:
    phase_stats = record.get("phase_stats")
    if not isinstance(phase_stats, dict):
        return []
    rows: List[str] = []
    for phase_name in sorted(phase_stats.keys()):
        stats = phase_stats.get(phase_name)
        if not isinstance(stats, dict):
            continue
        elapsed = stats.get("elapsed_ms") if isinstance(stats.get("elapsed_ms"), dict) else {}
        cpu = stats.get("cpu_ms") if isinstance(stats.get("cpu_ms"), dict) else {}
        rss = stats.get("rss_delta_kib") if isinstance(stats.get("rss_delta_kib"), dict) else {}
        rows.append(
            " | ".join(
                [
                    phase_name,
                    f"elapsed p50={_fmt_ms(elapsed.get('p50'))}",
                    f"elapsed p95={_fmt_ms(elapsed.get('p95'))}",
                    f"cpu p50={_fmt_ms(cpu.get('p50'))}",
                    f"cpu p95={_fmt_ms(cpu.get('p95'))}",
                    f"rss p95={_fmt_kib(rss.get('p95'))}",
                ]
            )
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Show latest ingestion profile summary.")
    parser.add_argument(
        "--path",
        default="data/observability/ingest_profiles.jsonl",
        help="Path to JSONL profile file.",
    )
    parser.add_argument(
        "--connector",
        default="",
        choices=("", "jira", "helix"),
        help="Filter by connector (jira/helix).",
    )
    args = parser.parse_args()

    records = _load_records(Path(args.path))
    if args.connector:
        records = [r for r in records if str(r.get("connector") or "").strip() == args.connector]
    if not records:
        print("No ingest profiles found.")
        return 0

    latest = records[-1]
    connector = str(latest.get("connector") or "unknown")
    run_id = int(latest.get("run_id") or 0)
    state = str(latest.get("state") or "unknown")
    summary = str(latest.get("summary") or "").strip()
    run_elapsed_ms = _fmt_ms(latest.get("run_elapsed_ms"))
    run_cpu_ms = _fmt_ms(latest.get("run_cpu_ms"))
    counters = latest.get("counters") if isinstance(latest.get("counters"), dict) else {}

    print(f"Connector: {connector}")
    print(f"Run ID: {run_id}")
    print(f"State: {state}")
    if summary:
        print(f"Summary: {summary}")
    print(f"Run elapsed: {run_elapsed_ms}")
    print(f"Run CPU: {run_cpu_ms}")
    if counters:
        print(f"Counters: {json.dumps(counters, ensure_ascii=False, sort_keys=True)}")
    print("Phase metrics:")
    rows = list(_iter_phase_rows(latest))
    if not rows:
        print("- (none)")
    else:
        for row in rows:
            print(f"- {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
