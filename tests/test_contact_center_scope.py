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
    reports = {segment: replace(report, file_name=f"{segment}.pptx", content=segment.encode()) for segment in ("PYME", "BEI")}
    projection = build_cloud_projection_artifact(settings, country="Argentina", source_ids=["helix:argentina:senda"], scope_mode="source", contact_center_report_results=reports).projection
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
    empty = build_cloud_projection_artifact(settings, country="Argentina", source_ids=["helix:argentina:senda"], scope_mode="source", contact_center_report_results=reports).projection["views"]["contactCenter"]
    assert empty["PYME"]["issues"]["total"] == 0
    assert empty["BEI"]["issues"]["total"] == 2


def test_segmented_report_transport_and_empty_segment(settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from io import BytesIO
    from pptx import Presentation
    from pptx.util import Inches
    from bug_resolution_radar.reports import service
    from bug_resolution_radar.services import data_transfer as transfer

    _populate(settings)
    seen = {}

    def render(_settings, **kwargs):
        segment = kwargs['contact_center']
        keys = kwargs['dff_override']['key'].tolist()
        seen[segment] = keys
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(2)).text = f'{segment}: {keys}'
        buffer = BytesIO()
        deck.save(buffer)
        return PeriodFollowupReportResult(
            file_name=f'{segment or "full"}.pptx', content=buffer.getvalue(), slide_count=1,
            total_issues=len(keys), open_issues=len(keys), closed_issues=0,
            country=kwargs['country'], source_ids=tuple(kwargs['source_ids']), applied_filter_summary='',
        )

    monkeypatch.setattr(service, 'generate_country_period_followup_ppt', render)
    def build():
        return build_cloud_projection_artifact(settings, country='Argentina', source_ids=['helix:argentina:senda'], scope_mode='source')

    def archive(artifact, *, include_bei=True):
        files = {'projection': artifact.projection_content, 'report': artifact.report_content}
        if include_bei and artifact.report_bei_content:
            files['reportBei'] = artifact.report_bei_content
        manifest = transfer._manifest(created_at=artifact.projection['generatedAt'], scope=artifact.projection['scope'], files=files)
        path = tmp_path / 'report.brr'
        path.write_bytes(transfer._build_archive(files, manifest))
        return path, manifest

    artifact = build()
    assert seen == {'PYME': ['INC-PYME'], 'BEI': ['INC-BEI']}
    path, manifest = archive(artifact)
    _, decoded = transfer._decode_archive(path)
    assert decoded['report'] != decoded['reportBei']
    projection = decoded['projection']
    for segment in ('PYME', 'BEI'):
        assert projection['contactCenterReports'][segment]['newsletterFacts']['draft']['subject'].startswith(f'[{segment}]')
    path, _ = archive(artifact, include_bei=False)
    with pytest.raises(transfer.TransferValidationError):
        transfer._decode_archive(path)

    root = Path(__file__).resolve().parents[1] / 'apps-script'
    script = '\n'.join((root / name).read_text(encoding='utf-8') for name in (
        '00_Config.gs', '20_Adapters.gs', '25_MaterializedSnapshots.gs', '10_Main.gs', '56_Newsletter.gs', '99_Core.gs'
    ))
    script += '\nconst projection = ' + json.dumps(projection, ensure_ascii=False) + ';\n'
    script += '\nconst manifest = ' + json.dumps(manifest, ensure_ascii=False) + ';\n'
    script += r"""
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
function _hash_(value) { return crypto.createHash('sha256').update(String(value)).digest('hex'); }
function _dayKey_(value) { return new Date(value).toISOString().slice(0,10); }
assert.equal(_validateProjection_(projection,manifest,manifest.datasets.report).scopeKey,projection.scope.scopeKey);
const broken=JSON.parse(JSON.stringify(manifest)); delete broken.datasets.reportBei;
assert.throws(()=>_validateProjection_(projection,broken,broken.datasets.report));
const altered=JSON.parse(JSON.stringify(projection)); altered.contactCenterReports.BEI.newsletterFacts.draft.subject='Incorrecto';
assert.throws(()=>_validateProjection_(altered,manifest,manifest.datasets.report));
const parts = _projectionPartValues_(projection);
const pub = segment => {
  const r = projection.contactCenterReports[segment].report;
  return {reportId: segment, reportName:r.fileName, pptxFileId:'pptx-'+segment, slidesFileId:'slides-'+segment, slidesUrl:'https://docs.google.com/presentation/d/'+segment+'/edit', pptxSha256:r.sha256,pptxBytes:r.bytes,slideCount:r.slideCount};
};
parts.meta.reportPublications = {PYME:pub('PYME'),BEI:pub('BEI')};
const record = {snapshot_id:'s',scope_key:projection.scope.scopeKey,scope_label:projection.scope.scopeLabel,country:projection.scope.country,data_version:projection.scope.dataVersion,projection_sha256:'p',report_id:'PYME',facts_sha256:projection.factsSha256,pptx_sha256:projection.report.sha256,slides_file_id:'slides-PYME',row_count:2};
function _snapshotHeader_() {return parts.meta;}
function _loadSnapshotPart_(_record,key) {return parts[key];}
function _snapshotRecordById_() {return record;}
const records = _snapshotReportRecords_(record);
const audits = records.map(_reportAuditFromSnapshot_);
function _readRecords_() {return audits;}
assert.equal(records.length,2);
assert.notEqual(records[0].scope_key,records[1].scope_key);
for (const segment of ['PYME','BEI']) {
  assert.equal(_snapshotReportRecord_(record,segment).report_id,segment);
  assert.ok(_newsletterContext_(segment).newsletter.draft.subject.startsWith('['+segment+']'));
}
const trashed=[]; let pointer=false; let calls=0;
function _activeSnapshotRecordForScope_(){return record;}
function _configuredReportDriveFolder_(){return {};}
function _dataVersion_(){return 'old';}
function _nowIso_(){return '2026-11-26T00:00:00Z';}
function _uuid_(){return 'id-'+calls;}
function _importExactReportArtifacts_(){calls++; if(calls===2)throw Error('second conversion');return pub('PYME');}
function _trashDriveFileQuietly_(id){trashed.push(id);}
function _deleteSnapshotChunkRows_(){}
function _deleteSnapshotPartRows_(){}
function _publishSnapshotPointer_(){pointer=true;}
assert.throws(()=>_publishDecodedTransfer_({scopeKey:record.scope_key,projectionSha256:'new',projection,reportBlob:{},reportBeiBlob:{}},{runId:'run'},{email:'test@example.com'}),/second conversion/);
assert.equal(pointer,false);
assert.deepEqual(trashed,['pptx-PYME','slides-PYME']);
"""
    result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr

    config.save_contact_center_pyme(settings, 'Argentina', config.ContactCenterConfig(enabled=True, people=[]))
    empty = build()
    assert empty.projection['views']['contactCenter']['PYME']['issues']['total'] == 0
    assert len(Presentation(BytesIO(empty.report_content)).slides) == 1
    path, _ = archive(empty)
    transfer._decode_archive(path)
    config.save_contact_center_pyme(settings, 'Argentina', config.ContactCenterConfig(enabled=False, people=[]))
    full = build()
    assert not full.report_bei_content
    assert 'contactCenterReports' not in full.projection
    path, manifest = archive(full)
    assert set(manifest['datasets']) == {'projection','report'}
    transfer._decode_archive(path)
