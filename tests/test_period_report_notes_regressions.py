from pathlib import Path

import pandas as pd

from bug_resolution_radar.analytics.finalist_discrepancy_lists import (
    build_finalist_discrepancy_issue_list,
)
from bug_resolution_radar.reports import period_followup_ppt as period_ppt_mod
from bug_resolution_radar.services.notes import NotesStore


def test_report_notes_use_latest_legacy_block_without_duplicate_chunks(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "notes.json"
    store_path.write_text(
        '{"SKSEMEX-102296": "Sin fecha:\\nNota antigua\\n\\n2026-07-02 10:41:\\nNota vigente"}',
        encoding="utf-8",
    )

    store = NotesStore(store_path)
    store.load()

    latest = store.latest("SKSEMEX-102296")
    assert latest == "2026-07-02 10:41:\nNota vigente"
    assert period_ppt_mod._issue_comment_chunks(latest) == (latest,)


def test_report_notes_are_truncated_to_single_ppt_table_row(tmp_path: Path) -> None:
    store = NotesStore(tmp_path / "notes.json")
    store.set("SKSEMEX-102296", f"Comentarios:\n{'x' * 500}")

    latest = store.latest("SKSEMEX-102296") or ""

    assert len(latest) <= period_ppt_mod._ISSUE_COMMENT_CHUNK_CHARS
    assert period_ppt_mod._issue_comment_chunks(latest) == (latest,)


def test_finalist_discrepancy_rows_are_unique_by_jira_key() -> None:
    discrepancies = pd.DataFrame(
        [
            {
                "jira_key": "sksemex-90706 ",
                "helix_id": "INC-A",
                "jira_priority": "High",
                "jira_open_days": 12,
                "jira_status": "In Progress",
            },
            {
                "jira_key": "SKSEMEX-90706",
                "helix_id": "INC-B",
                "jira_priority": "High",
                "jira_open_days": 12,
                "jira_status": "In Progress",
            },
        ]
    )

    rows = build_finalist_discrepancy_issue_list(discrepancies)

    assert [(row.jira_key, row.helix_id) for row in rows] == [("SKSEMEX-90706", "INC-A")]
