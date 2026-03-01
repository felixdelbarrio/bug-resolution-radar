from __future__ import annotations

from pathlib import Path

from bug_resolution_radar.services.ingest_circuit_breaker import IngestCircuitBreaker


def test_circuit_breaker_opens_and_recovers_after_cooldown(tmp_path: Path) -> None:
    state_path = tmp_path / "circuit.json"
    breaker = IngestCircuitBreaker(
        enabled=True,
        state_path=str(state_path),
        failure_threshold=2,
        window_seconds=60,
        cooldown_seconds=120,
        max_failure_events=20,
    )

    initial = breaker.allow(connector="jira", source_id="jira:mx:core", now_ts=1000.0)
    assert initial.allowed is True

    breaker.record_failure(
        connector="jira",
        source_id="jira:mx:core",
        message="timeout 1",
        now_ts=1001.0,
    )
    warmup = breaker.allow(connector="jira", source_id="jira:mx:core", now_ts=1001.5)
    assert warmup.allowed is True

    breaker.record_failure(
        connector="jira",
        source_id="jira:mx:core",
        message="timeout 2",
        now_ts=1002.0,
    )
    opened = breaker.allow(connector="jira", source_id="jira:mx:core", now_ts=1003.0)
    assert opened.allowed is False
    assert opened.reason == "open"
    assert opened.open_until_iso != ""

    # State is persisted and shared by new breaker instances.
    second_reader = IngestCircuitBreaker(
        enabled=True,
        state_path=str(state_path),
        failure_threshold=2,
        window_seconds=60,
        cooldown_seconds=120,
    )
    still_open = second_reader.allow(connector="jira", source_id="jira:mx:core", now_ts=1010.0)
    assert still_open.allowed is False

    after_cooldown = second_reader.allow(
        connector="jira",
        source_id="jira:mx:core",
        now_ts=1125.0,
    )
    assert after_cooldown.allowed is True

    second_reader.record_success(connector="jira", source_id="jira:mx:core", now_ts=1126.0)
    healthy = second_reader.allow(connector="jira", source_id="jira:mx:core", now_ts=1127.0)
    assert healthy.allowed is True
    assert healthy.consecutive_failures == 0
    assert healthy.recent_failures == 0


def test_circuit_breaker_prunes_failures_outside_window(tmp_path: Path) -> None:
    state_path = tmp_path / "circuit.json"
    breaker = IngestCircuitBreaker(
        enabled=True,
        state_path=str(state_path),
        failure_threshold=2,
        window_seconds=10,
        cooldown_seconds=30,
    )

    breaker.record_failure(
        connector="helix",
        source_id="helix:mx:core",
        message="network 1",
        now_ts=10.0,
    )
    breaker.record_failure(
        connector="helix",
        source_id="helix:mx:core",
        message="network 2",
        now_ts=25.0,
    )
    # First failure expired from the 10s window, breaker stays closed.
    mid = breaker.allow(connector="helix", source_id="helix:mx:core", now_ts=26.0)
    assert mid.allowed is True

    breaker.record_failure(
        connector="helix",
        source_id="helix:mx:core",
        message="network 3",
        now_ts=28.0,
    )
    opened = breaker.allow(connector="helix", source_id="helix:mx:core", now_ts=28.5)
    assert opened.allowed is False
