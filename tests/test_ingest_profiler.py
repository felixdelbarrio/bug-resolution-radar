from __future__ import annotations

import json
import time
from pathlib import Path

from bug_resolution_radar.services.ingest_profiler import IngestRunProfiler


def test_ingest_profiler_builds_phase_stats_and_persists_jsonl(tmp_path: Path) -> None:
    output_path = tmp_path / "profiles.jsonl"
    profiler = IngestRunProfiler(
        connector="jira",
        run_id=11,
        enabled=True,
        output_path=str(output_path),
    )

    with profiler.phase(phase="source_ingest", source_id="jira:mx:core", source_label="MX Core"):
        time.sleep(0.002)
    with profiler.phase(phase="source_ingest", source_id="jira:mx:core", source_label="MX Core"):
        time.sleep(0.001)
    with profiler.phase(phase="persist_results"):
        time.sleep(0.001)
    profiler.increment("sources_ok")
    profiler.increment("sources_ok")

    record = profiler.build_record(
        state="success",
        summary="ok",
        total_sources=1,
        success_count=1,
    )
    profiler.persist(record)

    assert output_path.exists() is True
    lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["connector"] == "jira"
    assert int(payload["run_id"]) == 11
    assert int(payload["sample_count"]) == 3

    source_ingest = payload["phase_stats"]["source_ingest"]
    elapsed_stats = source_ingest["elapsed_ms"]
    assert float(elapsed_stats["count"]) == 2.0
    assert float(elapsed_stats["p95"]) >= float(elapsed_stats["p50"])
    assert int(payload["counters"]["sources_ok"]) == 2


def test_ingest_profiler_noops_when_disabled(tmp_path: Path) -> None:
    output_path = tmp_path / "profiles.jsonl"
    profiler = IngestRunProfiler(
        connector="helix",
        run_id=1,
        enabled=False,
        output_path=str(output_path),
    )

    with profiler.phase(phase="source_ingest", source_id="helix:mx:core", source_label="MX"):
        time.sleep(0.001)

    record = profiler.build_record(
        state="success",
        summary="noop",
        total_sources=1,
        success_count=1,
    )
    profiler.persist(record)

    assert int(record["sample_count"]) == 0
    assert output_path.exists() is False
