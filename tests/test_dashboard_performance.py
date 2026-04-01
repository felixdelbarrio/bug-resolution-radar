from __future__ import annotations

from bug_resolution_radar.ui.dashboard import performance
from bug_resolution_radar.ui.dashboard.tabs import overview_tab, trends_tab


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.captions: list[str] = []

    def caption(self, text: str) -> None:
        self.captions.append(str(text))


def test_render_perf_footer_persists_snapshot_and_reports_overruns(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(performance, "st", fake_st)

    overruns = performance.render_perf_footer(
        snapshot_key="overview::perf_snapshot",
        view="Overview",
        ordered_blocks=["filters", "exports", "total"],
        metrics_ms={"filters": 120.0, "exports": 30.0, "total": 410.0},
        budgets_ms={"filters": 95.0, "exports": 45.0, "total": 380.0},
    )

    assert overruns == ["filters", "total"]
    snapshot = fake_st.session_state["overview::perf_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["view"] == "Overview"
    assert snapshot["overruns"] == ["filters", "total"]
    assert any("Perf Overview" in c for c in fake_st.captions)
    assert any("Budget excedido en: filters, total" in c for c in fake_st.captions)
    history = fake_st.session_state.get("__dashboard_perf_history")
    assert isinstance(history, list) and history
    assert history[-1]["snapshot_key"] == "overview::perf_snapshot"
    assert history[-1]["view"] == "Overview"


def test_render_perf_footer_can_persist_without_inline_captions(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(performance, "st", fake_st)

    overruns = performance.render_perf_footer(
        snapshot_key="overview::summary::perf_snapshot",
        view="Summary",
        ordered_blocks=["summary_charts", "summary_exports", "total"],
        metrics_ms={"summary_charts": 200.0, "summary_exports": 50.0, "total": 260.0},
        budgets_ms={"summary_charts": 280.0, "summary_exports": 70.0, "total": 420.0},
        emit_captions=False,
    )

    assert overruns == []
    assert fake_st.captions == []
    snapshots = performance.list_perf_snapshots()
    assert "overview::summary::perf_snapshot" in snapshots
    history = performance.perf_history_rows()
    assert len(history) == 1
    assert history[0]["view"] == "Summary"


def test_overview_perf_budget_falls_back_to_overview_default() -> None:
    assert overview_tab._overview_perf_budget(
        "not-configured"
    ) == overview_tab._overview_perf_budget("Overview")


def test_trends_perf_budget_falls_back_to_default_bucket() -> None:
    assert trends_tab._trends_perf_budget("not-configured") == trends_tab._trends_perf_budget(
        "default"
    )
