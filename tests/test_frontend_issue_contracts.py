from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _frontend_file(path: str) -> str:
    return (ROOT / "frontend" / "src" / path).read_text(encoding="utf-8")


def _function_block(source: str, name: str) -> str:
    start = source.index(f"function {name}")
    next_export = source.find("\nexport function", start + 1)
    return source[start:] if next_export == -1 else source[start:next_export]


def test_finalist_discrepancies_panel_has_no_filter_ui_or_state() -> None:
    source = _frontend_file("components/InsightsPanel.tsx")
    block = _function_block(source, "FinalistDiscrepanciesPanel")

    for token in ("Buscar", "Estado JIRA", "Estado Helix", "finalist-filter-grid"):
        assert token not in block
    for token in ("setSearch", "setJiraStatus", "setHelixStatus", "setPriority", "setAssignee"):
        assert token not in block
    assert "FilterCombo" not in block
    api_source = _frontend_file("lib/api.ts")
    finalist_type = api_source[
        api_source.index("finalistDiscrepancies:") : api_source.index(
            "people:", api_source.index("finalistDiscrepancies:")
        )
    ]
    assert "filterOptions" not in finalist_type


def test_finalist_discrepancies_renders_helix_text_and_right_counter() -> None:
    source = _frontend_file("components/InsightsPanel.tsx")
    styles = _frontend_file("styles/app.css")
    block = _function_block(source, "FinalistDiscrepanciesPanel")

    assert "finalist-helix-description" in block
    assert "group.helixText" in block
    assert "linkifyIssueReferences" in block
    assert "<strong>{group.jiraCount} JIRA</strong>" in block
    assert "finalist-summary-side" in styles
    assert "margin-left: auto" in styles


def test_issue_links_frontend_contract_uses_external_anchor_security() -> None:
    source = _frontend_file("lib/issueLinks.tsx")

    assert "export function buildJiraIssueUrl" in source
    assert "export function buildHelixIssueUrl" in source
    assert "export function linkifyIssueReferences" in source
    assert "https://jira.globaldevtools.bbva.com/browse" in source
    assert "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console" in source
    assert 'target="_blank"' in source
    assert 'rel="noopener noreferrer"' in source
    assert "INC\\d{8,}" in source
    assert "[A-Z][A-Z0-9]+-\\d+" in source


def test_issues_panel_exposes_functionality_and_helix_executive_description() -> None:
    source = _frontend_file("components/IssuesPanel.tsx")
    filters = _frontend_file("components/DashboardFilters.tsx")
    styles = _frontend_file("styles/app.css")

    assert '["functionality", "Funcionalidad"]' in source
    assert "row.functionality" in source
    assert "helix_executive_description" in source
    assert "BBVA_ExecutiveDescription" in source
    assert "issue-card-executive-description" in source
    assert "Funcionalidad" in filters
    assert "filterOptions?.functionality" in filters
    assert "issue-table-executive-description" in styles


def test_period_summary_frontend_uses_backend_delta_contract() -> None:
    api_source = _frontend_file("lib/api.ts")
    panel_source = _frontend_file("components/InsightsPanel.tsx")
    summary_block = panel_source[
        panel_source.index("data.periodSummary.cards.map") : panel_source.index(
            "data.periodSummary.groups.map"
        )
    ]

    assert "export type QuincenalDeltaPayload" in api_source
    assert "displayKind" in api_source
    assert "badgeText" in api_source
    assert "presentationBadgeText" in api_source
    assert "presentationSemanticTone" in api_source
    assert "relativeDelta" in api_source
    assert "delta?: QuincenalDeltaPayload | null" in api_source
    assert "card.detail" in summary_block
    assert "card.delta?.displayKind" in summary_block
    assert "card.delta.displayKind" not in summary_block
    assert "relativeDelta" not in summary_block
    assert "1400" not in summary_block


def test_dashboard_page_does_not_prefetch_heavy_inactive_panels() -> None:
    source = _frontend_file("pages/DashboardPage.tsx")

    assert "prefetchQuery" not in source
    assert "dashboard-intelligence" in source
    assert "insightsTab: dashboardState.params.insightsTab" in source
    assert "placeholderData: undefined" in source


def test_notes_editor_allows_free_issue_edit_and_validates_before_save() -> None:
    source = _frontend_file("components/NotesEditor.tsx")
    issue_on_change = source[
        source.index('list="notes-issue-suggestions"') : source.index("</label>")
    ]

    assert "setIssueDraft(event.target.value)" in issue_on_change
    assert "onIssueChange" not in issue_on_change
    assert "isValidIssueReference" in source
    assert "La nota no puede estar vacía" in source
    assert "Limpiar" in source


def test_notes_editor_splits_active_and_finalist_bitacoras() -> None:
    source = _frontend_file("components/NotesEditor.tsx")
    styles = _frontend_file("styles/app.css")
    semantics = _frontend_file("lib/statusSemantics.ts")

    assert "NOTE_BUCKETS" in source
    assert "En seguimiento" in source
    assert "Finalizadas" in source
    assert "issueLifecycleBucket(row.issue)" in source
    assert "selectedNotesRows.map" in source
    assert "notes-bucket-tabs" in styles
    assert "notes-index-stat-finalist" in styles
    assert "ready to deploy" in semantics
    assert "deployed" in semantics
    assert "closed" in semantics
