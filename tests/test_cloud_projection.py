from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pandas as pd
import pytest

from bug_resolution_radar.config import Settings
from bug_resolution_radar.reports.period_followup_ppt import PeriodFollowupReportResult
from bug_resolution_radar.services.cloud_projection import (
    _CLOUD_ACTION_KEYS,
    build_cloud_projection_artifact,
    canonical_json_bytes,
)


def _report(content: bytes = b"PK exact desktop report") -> PeriodFollowupReportResult:
    return PeriodFollowupReportResult(
        file_name="seguimiento-espana.pptx",
        content=content,
        slide_count=9,
        total_issues=2,
        open_issues=1,
        closed_issues=1,
        country="España",
        source_ids=("jira:espana:core",),
        applied_filter_summary="",
    )


def _intelligence(*, split: bool = True) -> dict[str, object]:
    cards: list[dict[str, object]] = [
        {
            "cardId": "new_now",
            "metric": "2",
            "delta": {"previousValue": 1},
            "issueKeys": ["RAD-1"],
        },
        {
            "cardId": "closed_now",
            "metric": "1",
            "delta": {"previousValue": 0},
        },
        {"cardId": "open_total", "metric": "3"},
        {"cardId": "resolution_now", "metric": "3.0d"},
    ]
    if split:
        cards.extend(
            [
                {"cardId": "open_focus", "metric": "2", "label": "Criticidad alta"},
                {"cardId": "open_other", "metric": "1", "label": "Otras"},
            ]
        )
    return {
        "tabs": [{"id": "summary", "label": "Resumen"}],
        "periodSummary": {
            "caption": "España · Periodo 01/07 - 14/07/2026",
            "showOpenSplit": split,
            "cards": cards,
        },
        "functionality": {
            "combo": {"statusOptions": ["Open"], "selectedStatuses": ["Open"]},
            "rows": [{"functionality": "Pagos", "count": 1}],
        },
        "duplicates": {},
        "rootCauseEvolutives": {},
        "finalistDiscrepancies": {},
        "people": {},
        "opsHealth": {},
    }


def _patch_materializers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    split: bool = True,
    issue_summary: str = "Detalle A",
) -> dict[str, object]:
    frame = pd.DataFrame(
        {
            "key": ["RAD-1", "RAD-2"],
            "created": ["2026-07-01", "2026-07-02"],
            "updated": ["2026-07-14", "2026-07-13"],
            "resolved": [None, "2026-07-12"],
        }
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.load_scope_context",
        lambda *_args, **_kwargs: SimpleNamespace(dff=frame),
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.build_dashboard_snapshot",
        lambda *_args, **_kwargs: {
            "overviewKpis": [{"label": "En cola > 30 días", "value": "1"}],
            "statusPriorityMatrix": {"selected": {"status": []}},
        },
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.build_intelligence_snapshot",
        lambda *_args, **_kwargs: _intelligence(split=split),
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.build_trend_detail",
        lambda *_args, chart_id, **_kwargs: {
            "chart": {"id": chart_id, "title": chart_id, "subtitle": "", "group": "g"},
            "cards": [{"statusFilters": ["Open"], "body": "Racional"}],
        },
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.build_issue_rows",
        lambda *_args, **_kwargs: {
            "total": 1,
            "rows": [
                {
                    "issue_uid": "jira:espana:core::RAD-1",
                    "key": "RAD-1",
                    "summary": issue_summary,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.build_kanban_columns",
        lambda *_args, **_kwargs: [
            {"status": "Open", "items": [{"key": "RAD-1", "priorityFilters": ["High"]}]}
        ],
    )
    captured: dict[str, object] = {}

    def fake_report(*_args: object, **kwargs: object) -> PeriodFollowupReportResult:
        captured.update(kwargs)
        return _report()

    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.generate_period_followup_report_artifact",
        fake_report,
    )
    return captured


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def test_projection_is_explicit_static_and_packages_exact_report_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_materializers(monkeypatch)

    artifact = build_cloud_projection_artifact(
        Settings(),
        country="España",
        source_ids=["jira:espana:core"],
        scope_mode="source",
        generated_at="2026-07-23T10:00:00+00:00",
    )

    projection = artifact.projection
    assert projection["scope"] == {
        "scopeKey": "espana::jira:espana:core",
        "scopeLabel": "España · jira:espana:core",
        "country": "España",
        "scopeMode": "source",
        "sourceIds": ["jira:espana:core"],
        "dataVersion": projection["scope"]["dataVersion"],
        "referenceDate": "2026-07-14",
        "immutable": True,
    }
    assert artifact.report_content == _report().content
    assert projection["report"]["sha256"] == hashlib.sha256(_report().content).hexdigest()
    assert captured["reference_day"] == "2026-07-14"
    assert captured["filters"].status == ()
    assert captured["filters"].priority == ()
    assert captured["filters"].assignee == ()
    assert not (_all_keys(projection["views"]) & _CLOUD_ACTION_KEYS)
    assert set(projection["views"]["trends"]) == {"catalog", "byId"}
    assert set(projection["views"]["insights"]) == {"catalog", "byId"}
    assert projection["views"]["kanban"][0]["items"][0]["issue_uid"] == "jira:espana:core::RAD-1"
    assert (
        projection["factsSha256"]
        == hashlib.sha256(canonical_json_bytes(projection["newsletterFacts"])).hexdigest()
    )


def test_newsletter_omits_false_open_split_when_desktop_hides_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_materializers(monkeypatch, split=False)
    projection = build_cloud_projection_artifact(
        Settings(),
        country="España",
        source_ids=["jira:espana:core"],
        scope_mode="source",
        report_result=_report(),
    ).projection

    newsletter = projection["newsletterFacts"]
    assert "focusOpen" not in newsletter["metrics"]
    assert "otherOpen" not in newsletter["metrics"]
    assert "focus" not in {fact["id"] for fact in newsletter["facts"]}


def test_data_version_changes_when_materialized_detail_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_materializers(monkeypatch, issue_summary="Detalle A")
    first = build_cloud_projection_artifact(
        Settings(),
        country="España",
        source_ids=["jira:espana:core"],
        scope_mode="source",
        report_result=_report(),
    ).projection["scope"]["dataVersion"]
    _patch_materializers(monkeypatch, issue_summary="Detalle B")
    second = build_cloud_projection_artifact(
        Settings(),
        country="España",
        source_ids=["jira:espana:core"],
        scope_mode="source",
        report_result=_report(),
    ).projection["scope"]["dataVersion"]

    assert first != second
