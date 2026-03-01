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


def test_overview_perf_budget_falls_back_to_overview_default() -> None:
    assert overview_tab._overview_perf_budget(
        "not-configured"
    ) == overview_tab._overview_perf_budget("Overview")


def test_trends_perf_budget_falls_back_to_default_bucket() -> None:
    assert trends_tab._trends_perf_budget("not-configured") == trends_tab._trends_perf_budget(
        "default"
    )
