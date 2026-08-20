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
        "tabs": [
            {"id": "evolution", "label": "Evolución"},
            {"id": "summary", "label": "Resumen"},
            {"id": "opsHealth", "label": "Salud operativa"},
        ],
        "executionEvolution": {
            "hasData": True,
            "referenceDate": "2026-07-14",
            "year": 2026,
            "executive": {
                "tone": "negative",
                "title": "Backlog incrementado en 1 durante la quincena",
                "summary": (
                    "El backlog pasa de 2 a 3. La cartera abierta media sube de 2,1 a 2,6 "
                    "y cierra en 3. El tiempo medio de resolución mejora: baja 1,0 días, "
                    "de 4,0 a 3,0."
                ),
                "focus": ["Antigüedad: 1 abierta supera 30 días."],
            },
            "annual": {"label": "Evolución 2026"},
            "fortnight": {
                "current": {
                    "label": "01-14 JUL",
                    "backlogStart": 2,
                    "backlogEnd": 3,
                    "created": 2,
                    "closed": 1,
                    "resolutionDays": 3.0,
                    "averageOpen": 2.6,
                    "criticalOpen": 2,
                    "aged30Open": 1,
                },
                "previous": {
                    "created": 1,
                    "closed": 0,
                    "resolutionDays": 4.0,
                    "averageOpen": 2.1,
                },
            },
            "period": {},
            "timeline": [],
            "learning": {"comparison": []},
        },
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
    open_frame = pd.DataFrame(
        {
            "issue_uid": ["jira:espana:core::RAD-1"],
            "key": ["RAD-1"],
            "source_id": ["jira:espana:core"],
            "po_team_leader": ["Ana Responsable"],
            "priority": ["High"],
        }
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.load_scope_context",
        lambda *_args, **_kwargs: SimpleNamespace(
            dff=frame,
            open_df=open_frame,
            root_cause_evolutives=pd.DataFrame(
                {
                    "jira_key": ["RAD-1"],
                    "source_id": ["jira:espana:core"],
                    "po_team_leader": ["Ana Responsable"],
                }
            ),
            finalist_discrepancies=pd.DataFrame(
                columns=["jira_key", "source_id", "po_team_leader"]
            ),
        ),
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.jira_sources",
        lambda *_args, **_kwargs: [
            {
                "source_id": "jira:espana:core",
                "country": "España",
                "alias": "Core",
                "po_team_leader": "Ana Responsable",
                "dashboard_url": "https://jira.example.com/dashboard/1",
            }
        ],
    )
    monkeypatch.setattr(
        "bug_resolution_radar.services.cloud_projection.build_dashboard_snapshot",
        lambda *_args, **_kwargs: {
            "overviewKpis": [{"label": "En cola > 30 días", "value": "1"}],
            "charts": [
                {"id": chart_id, "figure": {"data": [{"x": [1]}]}}
                for chart_id in (
                    "timeseries",
                    "age_buckets",
                    "open_status_bar",
                    "open_priority_pie",
                    "resolution_hist",
                )
            ],
            "statusPriorityMatrix": {
                "total": 2,
                "priorities": [{"priority": "High", "count": 2}],
                "rows": [
                    {
                        "status": "Open",
                        "count": 1,
                        "cells": [{"priority": "High", "count": 1}],
                    },
                    {
                        "status": "Closed",
                        "count": 1,
                        "cells": [{"priority": "High", "count": 1}],
                    },
                    {
                        "status": "Discarded",
                        "count": 1,
                        "cells": [{"priority": "High", "count": 1}],
                    },
                    {
                        "status": "Deleted",
                        "count": 1,
                        "cells": [{"priority": "High", "count": 1}],
                    },
                ],
                "selected": {"status": []},
            },
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
            "total": 3,
            "rows": [
                {
                    "issue_uid": "jira:espana:core::RAD-1",
                    "key": "RAD-1",
                    "summary": issue_summary,
                    "url": "https://jira.example.com/browse/RAD-1",
                    "status": "Open",
                    "priority": "High",
                },
                {
                    "issue_uid": "jira:espana:core::RAD-2",
                    "key": "RAD-2",
                    "summary": "Descartada",
                    "url": "https://jira.example.com/browse/RAD-2",
                    "status": "Discarded",
                    "priority": "High",
                },
                {
                    "issue_uid": "jira:espana:core::RAD-3",
                    "key": "RAD-3",
                    "summary": "Eliminada",
                    "url": "https://jira.example.com/browse/RAD-3",
                    "status": "Deleted",
                    "priority": "High",
                },
            ],
        },
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
    assert set(projection["views"]) == {"overview", "insights", "trends", "issues"}
    summary_card = projection["views"]["insights"]["byId"]["summary"]["periodSummary"]["cards"][0]
    assert "issueKeys" not in summary_card
    assert summary_card["issues"][0]["url"] == "https://jira.example.com/browse/RAD-1"
    assert projection["views"]["overview"]["statusPriorityMatrix"]["total"] == 1
    assert projection["views"]["overview"]["statusPriorityMatrix"]["priorities"] == [
        {"priority": "High", "count": 1}
    ]
    assert projection["views"]["issues"]["total"] == 1
    assert [row["status"] for row in projection["views"]["issues"]["rows"]] == ["Open"]
    assert projection["administration"]["jiraSources"][0]["dashboardUrl"] == (
        "https://jira.example.com/dashboard/1"
    )
    assert projection["newsletterFacts"]["responsibleRollups"] == [
        {
            "name": "Ana Responsable",
            "dashboardUrl": "https://jira.example.com/dashboard/1",
            "openIssues": 1,
            "rootCauseEvolutives": 1,
            "finalistDiscrepancies": 0,
        }
    ]
    assert projection["newsletterFacts"]["previousOpen"] == 2
    assert projection["newsletterFacts"]["backlogDelta"] == 1
    assert projection["newsletterFacts"]["evolution"]["title"] == (
        "Backlog incrementado en 1 durante la quincena"
    )
    evolution = projection["views"]["insights"]["byId"]["evolution"]["executionEvolution"]
    assert evolution["fortnight"]["current"]["averageOpen"] == 2.6
    assert "cartera abierta media" in projection["newsletterFacts"]["evolution"]["summary"].lower()
    assert (
        "tiempo medio de resolución mejora"
        in projection["newsletterFacts"]["draft"]["summary"].lower()
    )
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
    assert newsletter["focusLabel"] == ""


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
