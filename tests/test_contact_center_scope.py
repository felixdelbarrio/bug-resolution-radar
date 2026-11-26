"""Regression tests for complementary Contact Center analytics and transport."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess

import pandas as pd
import pytest

from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import save_issues_doc
from bug_resolution_radar.services import contact_center_pyme as config
from bug_resolution_radar.services import dashboard_snapshot as dashboard
from bug_resolution_radar.services.cloud_projection import (
    _projection_query,
    build_cloud_projection_artifact,
)
from bug_resolution_radar.services.contact_center_scope import apply_contact_center_filter
from bug_resolution_radar.services.notes import NotesStore
from bug_resolution_radar.reports.period_followup_ppt import PeriodFollowupReportResult
from bug_resolution_radar.reports.service import _build_context_for_scope, build_report_filters


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(config, "config_home", lambda: tmp_path)
    result = Settings(
        DATA_PATH=str(tmp_path / "issues.json"),
        HELIX_DATA_PATH=str(tmp_path / "helix.json"),
        NOTES_PATH=str(tmp_path / "notes.json"),
    )
    config.save_contact_center_pyme(
        result, "Argentina", config.ContactCenterConfig(
            enabled=True, people=[config.ContactCenterPerson(
                legajo="A001", name="Synthetic operator", mail="test@example.com"
            )],
        )
    )
    dashboard.invalidate_scope_context_cache()
    return result


def test_partition_exact_login_and_disabled_country(settings: Settings) -> None:
    frame = pd.DataFrame({
        "key": ["A", "B", "C", "D", "E", "F"],
        "submitter": ["a001", " A001 ", "A0012", "", None, "test@example.com"],
        "reporter": ["", "", "A001", "A001", "A001", "A001"],
    })
    def selected(segment: str, country: str = "Argentina") -> set[str]:
        return set(apply_contact_center_filter(
            frame, settings=settings, country=country, selection=segment
        )["key"])
    assert selected("PYME") == {"A", "B"}
    assert selected("BEI") == {"C", "D", "E", "F"}
    assert selected("") == set(frame["key"])
    assert selected("PYME", "España") == set(frame["key"])
    config.save_contact_center_pyme(settings, "Argentina", config.ContactCenterConfig(enabled=False, people=[]))
    assert selected("PYME") == set(frame["key"])
    assert selected("BEI") == set(frame["key"])


def test_legacy_raw_submitter_only_matches_composite_identity(settings: Settings) -> None:
    HelixRepo(Path(settings.HELIX_DATA_PATH)).save(HelixDocument(items=[
        HelixWorkItem(id="INC1", country="Argentina", source_id="helix:argentina:a", raw_fields={"Submitter": "A001"}),
    ]))
    frame = pd.DataFrame({
        "key": ["INC1", "INC1", "INC1", "INC2"],
        "country": ["Argentina", "Argentina", "España", "Argentina"],
        "source_type": ["helix", "helix", "helix", "jira"],
        "source_id": ["helix:argentina:a", "helix:argentina:b", "helix:argentina:a", "jira:argentina:a"],
        "submitter": ["", "", "", ""],
    })
    pyme = apply_contact_center_filter(frame, settings=settings, country="Argentina", selection="PYME")
    assert list(pyme.index) == [0]
    assert NormalizedIssue(key="X", summary="test", status="New", type="Bug", priority="High", Submitter="A001").submitter == "A001"


def _populate(settings: Settings) -> None:
    stamp = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    issues = [
        NormalizedIssue(key=key, summary=f"Synthetic {key}", status="New", type="Incident",
                        priority="High", created=stamp, updated=stamp, country="Argentina",
                        source_type="helix", source_id="helix:argentina:senda", source_alias="Senda",
                        submitter=login)
        for key, login in [("INC-PYME", "A001"), ("INC-BEI", "OTHER")]
    ]
    save_issues_doc(settings.DATA_PATH, IssuesDocument(issues=issues))
    notes = NotesStore(Path(settings.NOTES_PATH))
    notes.load()
    notes.set("INC-PYME", "Nota PYME")
    notes.set("INC-BEI", "Nota BEI")
    notes.save()


def test_actual_analytics_and_cloud_full_partition(settings: Settings) -> None:
    _populate(settings)
    query = _projection_query(country="Argentina", scope_mode="source", source_ids=["helix:argentina:senda"])
    assert dashboard.build_issue_rows(settings, query=query)["total"] == 2
    for segment, key in [("PYME", "INC-PYME"), ("BEI", "INC-BEI")]:
        scoped = replace(query, contact_center=segment)
        rows = dashboard.build_issue_rows(settings, query=scoped)
        assert rows["total"] == 1
        assert rows["rows"][0]["key"] == key
        assert key in {item["key"] for column in dashboard.build_kanban_columns(settings, query=scoped) for item in column["items"]}
        assert dashboard.load_scope_context(settings, query=scoped).dff["key"].tolist() == [key]
        report_context = _build_context_for_scope(
            settings, country="Argentina", source_ids=["helix:argentina:senda"],
            filters=build_report_filters(contact_center=segment),
        )
        assert report_context.all_df["key"].tolist() == [key]
        assert report_context.dff["key"].tolist() == [key]
    report = PeriodFollowupReportResult(file_name="synthetic.pptx", content=b"synthetic report", slide_count=1, total_issues=2, open_issues=2, closed_issues=0, country="Argentina", source_ids=("helix:argentina:senda",), applied_filter_summary="")
    projection = build_cloud_projection_artifact(settings, country="Argentina", source_ids=["helix:argentina:senda"], scope_mode="source", report_result=report).projection
    full = projection["views"]
    assert full["issues"]["total"] == 2
    assert full["overview"]["stats"]["issues_total"] == 2
    assert projection["semantics"]["contactCenterMaterialized"] is True
    for segment, key in [("PYME", "INC-PYME"), ("BEI", "INC-BEI")]:
        variant = full["contactCenter"][segment]
        assert variant["issues"]["total"] == 1
        assert variant["overview"]["stats"]["issues_total"] == 1
        assert variant["overview"]["stats"]["issues_open"] == 1
        assert variant["issues"]["rows"][0]["key"] == key
        assert variant["notes"][0]["key"] == key
        assert {item["key"] for column in variant["kanban"] for item in column["items"]} == {key}
        assert set(variant) == {"overview", "insights", "trends", "issues", "kanban", "notes"}
    # Execute the actual Apps Script section materializer and read adapter in Node.
    # No Apps Script services are needed: the stored sectional parts are in memory.
    root = Path(__file__).resolve().parents[1] / "apps-script"
    script = "\n".join((root / name).read_text(encoding="utf-8") for name in (
        "00_Config.gs", "20_Adapters.gs", "25_MaterializedSnapshots.gs", "99_Core.gs"
    ))
    script += "\nconst projection = " + json.dumps(projection, ensure_ascii=False) + ";\n"
    script += r"""
const assert = require('node:assert/strict');
const parts = _projectionPartValues_(projection);
const record = { snapshot_id: 'synthetic', scope_key: projection.scope.scopeKey, data_version: '1' };
function _snapshotHeader_() { return parts.meta; }
function _loadSnapshotPart_(_record, key) { assert.ok(key in parts, key); return parts[key]; }
function _configuredSummaryChartIds_() { return ['timeseries', 'open_priority_pie', 'resolution_hist']; }
const rootViews = { ...projection.views }; delete rootViews.contactCenter;
assert.equal(_validateMaterializedViews_(rootViews, false).size, 2);
for (const [segment, key, other] of [['PYME', 'INC-PYME', 'INC-BEI'], ['BEI', 'INC-BEI', 'INC-PYME']]) {
  assert.equal(_validateMaterializedViews_(projection.views.contactCenter[segment], true).size, 1);
  const request = view => _normalizeMaterializedRequest_({scopeKey: record.scope_key, contactCenter: segment, view});
  for (const view of ['overview', 'insights', 'trends', 'issues', 'kanban', 'notes']) {
    const response = _materializedViewPayload_(record, request(view));
    assert.equal(response.contactCenter, segment);
    if (view === 'overview') assert.equal(response.stats.issues_total, 1);
    if (view === 'issues') { assert.equal(response.totalRows, 1); assert.equal(response.rows[0].key, key); }
    if (view === 'notes') assert.equal(response.notes[0].key, key);
    if (view === 'kanban') assert.equal(response.kanban[0].items[0].key, key);
  }
  assert.equal(_snapshotIssueDetail_(record, 'helix:argentina:senda::' + key, segment).key, key);
  assert.equal(_snapshotIssueDetail_(record, 'helix:argentina:senda::' + other, segment), null);
}
assert.equal(_snapshotContactCenterPrefix_(record, ''), 'contact-center/PYME/');
assert.throws(() => _snapshotContactCenterPrefix_(record, 'OTHER'));
"""
    result = subprocess.run(["node", "-"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    # Reclassify without ingesting again: roster edits invalidate cached scopes.
    config.save_contact_center_pyme(settings, "Argentina", config.ContactCenterConfig(enabled=True, people=[]))
    assert dashboard.build_issue_rows(settings, query=replace(query, contact_center="PYME"))["total"] == 0
    assert dashboard.build_issue_rows(settings, query=replace(query, contact_center="BEI"))["total"] == 2
    empty = build_cloud_projection_artifact(settings, country="Argentina", source_ids=["helix:argentina:senda"], scope_mode="source", report_result=report).projection["views"]["contactCenter"]
    assert empty["PYME"]["issues"]["total"] == 0
    assert empty["BEI"]["issues"]["total"] == 2
