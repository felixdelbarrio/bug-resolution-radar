from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.analytics.filtering import FilterState
from bug_resolution_radar.analytics.period_summary import build_country_quincenal_result
from bug_resolution_radar.config import Settings
from bug_resolution_radar.services import dashboard_snapshot
from bug_resolution_radar.services.dashboard_snapshot import (
    DashboardQuery,
    build_dashboard_snapshot,
    build_intelligence_snapshot,
    build_issue_rows,
)
from bug_resolution_radar.services.workspace import WorkspaceSelection


def test_build_issue_rows_skips_kpi_computation(monkeypatch: Any, tmp_path) -> None:
    settings = Settings(DATA_PATH=str(tmp_path / "issues.json"))
    query = DashboardQuery(
        workspace=WorkspaceSelection(country="México", source_id="jira:mexico:core"),
        filters=FilterState(status=[], priority=[], assignee=[]),
    )
    scoped_df = pd.DataFrame(
        [
            {
                "key": "MEX-2",
                "summary": "Segunda",
                "description": "Detalle",
                "status": "New",
                "type": "Bug",
                "priority": "High",
                "assignee": "Ana",
                "created": "2026-04-01T10:00:00Z",
                "updated": "2026-04-03T10:00:00Z",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "https://jira.local/browse/MEX-2",
            },
            {
                "key": "MEX-1",
                "summary": "Primera",
                "description": "Detalle",
                "status": "Blocked",
                "type": "Bug",
                "priority": "Medium",
                "assignee": "Luis",
                "created": "2026-04-01T10:00:00Z",
                "updated": "2026-04-02T10:00:00Z",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "https://jira.local/browse/MEX-1",
            },
        ]
    )

    monkeypatch.setattr(
        dashboard_snapshot,
        "load_workspace_dataframe",
        lambda settings, *, query: scoped_df,
    )

    def _fail_compute_kpis(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("build_issue_rows no debe calcular KPIs")

    monkeypatch.setattr(dashboard_snapshot, "compute_kpis", _fail_compute_kpis)
    dashboard_snapshot._scope_context_cache.clear()

    out = build_issue_rows(
        settings, query=query, offset=0, limit=1, sort_by="updated", sort_dir="desc"
    )

    assert out["total"] == 2
    assert [row["key"] for row in out["rows"]] == ["MEX-2"]
    assert [row["issue_uid"] for row in out["rows"]] == ["jira:mexico:core::MEX-2"]


def test_intelligence_payload_includes_finalist_discrepancies_tab(
    monkeypatch: Any,
    tmp_path,
) -> None:
    settings = Settings(DATA_PATH=str(tmp_path / "issues.json"))
    query = DashboardQuery(
        workspace=WorkspaceSelection(
            country="México",
            source_id="jira:mexico:core",
            scope_mode="country",
        ),
        filters=FilterState(status=[], priority=[], assignee=[]),
    )
    df = pd.DataFrame(
        [
            {
                "key": "MEX-1",
                "summary": "Jira pendiente",
                "description": "Helix INC000104154954",
                "status": "To Rework",
                "priority": "High",
                "assignee": "Ana",
                "created": "2026-05-01T10:00:00Z",
                "updated": "2026-05-04T10:00:00Z",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "https://jira.local/browse/MEX-1",
            },
            {
                "key": "MEX-2",
                "summary": "Jira pendiente 2",
                "description": "Helix INC000104154954",
                "status": "Open",
                "priority": "High",
                "assignee": "Bea",
                "created": "2026-04-29T10:00:00Z",
                "updated": "2026-05-04T10:00:00Z",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "https://jira.local/browse/MEX-2",
            },
            {
                "key": "INC000104154954",
                "summary": "Helix cerrado",
                "description": "Detalle INC000104154954",
                "status": "Closed",
                "priority": "High",
                "created": "2026-04-30T10:00:00Z",
                "updated": "2026-05-03T10:00:00Z",
                "resolved": "2026-05-03T10:00:00Z",
                "source_type": "helix",
                "source_alias": "Lookup estados finalistas Jira",
                "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                "helix_lookup_kind": "post_jql_inc_lookup",
                "country": "México",
                "url": "https://helix.local/INC000104154954",
            },
        ]
    )
    monkeypatch.setattr(dashboard_snapshot, "load_workspace_dataframe", lambda *_a, **_k: df)
    monkeypatch.setattr(dashboard_snapshot, "load_country_dataframe", lambda *_a, **_k: df)
    dashboard_snapshot._scope_context_cache.clear()

    payload = build_intelligence_snapshot(settings, query=query)

    assert [tab["id"] for tab in payload["tabs"]][2:5] == [
        "duplicates",
        "rootCauseEvolutives",
        "finalistDiscrepancies",
    ]
    discrepancies = payload["finalistDiscrepancies"]
    assert discrepancies["totalRows"] == 2
    assert discrepancies["groups"][0]["helixId"] == "INC000104154954"
    assert discrepancies["groups"][0]["helixText"] == "Helix cerrado\nDetalle INC000104154954"
    assert discrepancies["groups"][0]["jiraCount"] == 2
    assert {issue["key"] for issue in discrepancies["groups"][0]["issues"]} == {"MEX-1", "MEX-2"}


def test_intelligence_period_summary_reuses_central_quincenal_delta(
    monkeypatch: Any,
    tmp_path,
) -> None:
    reference_day = pd.Timestamp("2026-03-20T00:00:00+00:00")
    rows: list[dict[str, object]] = [
        {
            "key": "PREV-1",
            "summary": "Referencia mínima",
            "description": "",
            "status": "Resolved",
            "priority": "High",
            "assignee": "Ana",
            "created": "2026-03-02T00:00:00+00:00",
            "updated": "2026-03-02T00:30:00+00:00",
            "resolved": "2026-03-02T00:30:00+00:00",
            "source_type": "jira",
            "source_alias": "Core",
            "source_id": "jira:mexico:core",
            "country": "México",
            "url": "",
        }
    ]
    for idx in range(15):
        day = 15 + (idx % 6)
        rows.append(
            {
                "key": f"CUR-{idx + 1}",
                "summary": "Actual",
                "description": "",
                "status": "New",
                "priority": "Medium",
                "assignee": "Ana",
                "created": f"2026-03-{day:02d}T00:00:00+00:00",
                "updated": f"2026-03-{day:02d}T00:00:00+00:00",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "",
            }
        )
    df = pd.DataFrame(rows)
    settings = Settings(DATA_PATH=str(tmp_path / "issues.json"))
    query = DashboardQuery(
        workspace=WorkspaceSelection(
            country="México",
            source_id="jira:mexico:core",
            scope_mode="country",
        ),
        filters=FilterState(status=[], priority=[], assignee=[]),
    )
    expected = build_country_quincenal_result(
        df=df,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:core"],
        reference_day=reference_day,
    ).aggregate.summary
    quincenal_calls = 0

    def _counted_quincenal_result(*args: Any, **kwargs: Any) -> Any:
        nonlocal quincenal_calls
        quincenal_calls += 1
        return build_country_quincenal_result(*args, **kwargs)

    monkeypatch.setattr(dashboard_snapshot, "load_workspace_dataframe", lambda *_a, **_k: df)
    monkeypatch.setattr(dashboard_snapshot, "load_country_dataframe", lambda *_a, **_k: df)
    monkeypatch.setattr(dashboard_snapshot, "load_country_history_dataframe", lambda *_a, **_k: df)
    monkeypatch.setattr(
        dashboard_snapshot,
        "build_country_quincenal_result",
        _counted_quincenal_result,
    )
    monkeypatch.setattr(
        "bug_resolution_radar.analytics.period_summary.TimeWindowService.today",
        lambda self: reference_day.tz_localize(None),
    )
    dashboard_snapshot._scope_context_cache.clear()

    payload = build_intelligence_snapshot(settings, query=query)
    created_card = next(
        card for card in payload["periodSummary"]["cards"] if card["cardId"] == "new_now"
    )

    assert created_card["detail"] == expected.new_delta.display_text
    assert created_card["delta"] == expected.new_delta.to_payload()
    assert created_card["delta"]["displayKind"] == "absolute"
    assert created_card["delta"]["relativeDelta"] == 14.0
    assert created_card["delta"]["presentationBadgeText"] == "▲>100%"
    assert created_card["delta"]["presentationSemanticTone"] == "risk"
    assert "1400" not in created_card["detail"]
    assert quincenal_calls == 1
    assert any(
        card["cardId"] == "open_total" and card["delta"] is None
        for card in payload["periodSummary"]["cards"]
    )


def test_intelligence_summary_tab_skips_inactive_heavy_payloads(
    monkeypatch: Any,
    tmp_path,
) -> None:
    reference_day = pd.Timestamp("2026-03-20T00:00:00+00:00")
    df = pd.DataFrame(
        [
            {
                "key": "CUR-1",
                "summary": "Actual",
                "description": "",
                "status": "New",
                "priority": "Medium",
                "assignee": "Ana",
                "created": "2026-03-18T00:00:00+00:00",
                "updated": "2026-03-18T00:00:00+00:00",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "",
            }
        ]
    )
    settings = Settings(DATA_PATH=str(tmp_path / "issues.json"))
    query = DashboardQuery(
        workspace=WorkspaceSelection(
            country="México",
            source_id="jira:mexico:core",
            scope_mode="country",
        ),
        filters=FilterState(status=[], priority=[], assignee=[]),
    )

    def _fail_inactive_builder(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("summary tab should not build inactive insight payloads")

    monkeypatch.setattr(dashboard_snapshot, "load_workspace_dataframe", lambda *_a, **_k: df)
    monkeypatch.setattr(dashboard_snapshot, "load_country_dataframe", lambda *_a, **_k: df)
    monkeypatch.setattr(dashboard_snapshot, "load_country_history_dataframe", lambda *_a, **_k: df)
    monkeypatch.setattr(dashboard_snapshot, "_build_functionality_payload", _fail_inactive_builder)
    monkeypatch.setattr(dashboard_snapshot, "_build_duplicates_payload", _fail_inactive_builder)
    monkeypatch.setattr(dashboard_snapshot, "_build_people_payload", _fail_inactive_builder)
    monkeypatch.setattr(dashboard_snapshot, "_build_ops_health_payload", _fail_inactive_builder)
    monkeypatch.setattr(
        dashboard_snapshot,
        "_build_finalist_discrepancies_payload",
        _fail_inactive_builder,
    )
    monkeypatch.setattr(
        "bug_resolution_radar.analytics.period_summary.TimeWindowService.today",
        lambda self: reference_day.tz_localize(None),
    )
    dashboard_snapshot._scope_context_cache.clear()

    payload = build_intelligence_snapshot(settings, query=query, insights_tab="summary")

    assert payload["periodSummary"]["cards"]
    assert payload["functionality"]["topics"] == []
    assert payload["duplicates"]["titleGroups"] == []
    assert payload["people"]["cards"] == []
    assert payload["opsHealth"]["kpis"] == []


def test_country_finalist_mode_updates_open_kpis_consistently(
    monkeypatch: Any,
    tmp_path,
) -> None:
    query = DashboardQuery(
        workspace=WorkspaceSelection(country="México", source_id="jira:mexico:core"),
        filters=FilterState(status=[], priority=[], assignee=[]),
        chart_ids=(),
    )
    df_selected = pd.DataFrame(
        [
            {
                "key": "MEX-1",
                "summary": "Jira pendiente",
                "description": "Helix INC000104154954",
                "status": "To Rework",
                "priority": "High",
                "created": "2026-05-01T10:00:00Z",
                "updated": "2026-05-04T10:00:00Z",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
            }
        ]
    )
    df_country = pd.concat(
        [
            df_selected,
            pd.DataFrame(
                [
                    {
                        "key": "INC000104154954",
                        "summary": "Helix cerrado",
                        "description": "Detalle",
                        "status": "Closed",
                        "priority": "High",
                        "created": "2026-04-30T10:00:00Z",
                        "updated": "2026-05-03T10:00:00Z",
                        "resolved": "2026-05-03T10:00:00Z",
                        "source_type": "helix",
                        "source_alias": "Lookup estados finalistas Jira",
                        "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                        "helix_lookup_kind": "post_jql_inc_lookup",
                        "country": "México",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    monkeypatch.setattr(
        dashboard_snapshot,
        "load_workspace_dataframe",
        lambda *_a, **_k: df_selected,
    )
    monkeypatch.setattr(
        dashboard_snapshot,
        "load_country_dataframe",
        lambda *_a, **_k: df_country,
    )

    dashboard_snapshot._scope_context_cache.clear()
    selected_payload = build_dashboard_snapshot(
        Settings(DATA_PATH=str(tmp_path / "issues.json")),
        query=query,
    )
    dashboard_snapshot._scope_context_cache.clear()
    country_payload = build_dashboard_snapshot(
        Settings(DATA_PATH=str(tmp_path / "issues.json")),
        query=query,
    )

    assert selected_payload["stats"]["issues_open"] == 0
    assert selected_payload["stats"]["issues_closed"] == 1
    assert country_payload["stats"]["issues_open"] == 0
    assert country_payload["stats"]["issues_closed"] == 1
