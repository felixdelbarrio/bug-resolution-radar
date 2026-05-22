"""Report row builders for finalist-state discrepancies."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from bug_resolution_radar.analytics.issues import priority_rank, status_progress_rank


@dataclass(frozen=True)
class FinalistDiscrepancyIssueRow:
    jira_key: str
    jira_summary: str
    jira_status: str
    jira_priority: str
    jira_assignee: str
    jira_open_days: int
    jira_url: str
    helix_id: str
    helix_summary: str
    helix_description: str
    helix_status: str
    helix_url: str
    source_alias: str = ""
    po_team_leader: str = ""

    @property
    def helix_text(self) -> str:
        summary = str(self.helix_summary or "").strip()
        description = str(self.helix_description or "").strip()
        helix_id = str(self.helix_id or "").strip().upper()
        parts: list[str] = []
        for value in (summary, description):
            if value.strip().upper() == helix_id:
                continue
            if value and value not in parts:
                parts.append(value)
        return "\n".join(parts) if parts else "Sin descripción Helix"


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _text(row: pd.Series, column: str) -> str:
    return str(row.get(column, "") or "").strip()


def build_finalist_discrepancy_issue_list(
    discrepancies: pd.DataFrame | None,
) -> tuple[FinalistDiscrepancyIssueRow, ...]:
    """Return discrepancies sorted for Excel/PPT consumption."""
    safe = _safe_df(discrepancies)
    if safe.empty:
        return ()

    work = safe.copy(deep=False)
    if "jira_priority" in work.columns:
        work["__priority_rank"] = work["jira_priority"].map(priority_rank).fillna(99)
    else:
        work["__priority_rank"] = 99
    if "jira_open_days" in work.columns:
        work["__open_days"] = pd.to_numeric(work["jira_open_days"], errors="coerce").fillna(0.0)
    else:
        work["__open_days"] = 0.0
    if "jira_status" in work.columns:
        work["__status_rank"] = work["jira_status"].map(status_progress_rank).fillna(99)
    else:
        work["__status_rank"] = 99
    for column in ("jira_key", "helix_id"):
        if column not in work.columns:
            work[column] = ""

    work = work.sort_values(
        by=["__priority_rank", "__open_days", "__status_rank", "helix_id", "jira_key"],
        ascending=[True, False, True, True, True],
        kind="mergesort",
    )

    rows: list[FinalistDiscrepancyIssueRow] = []
    for _, row in work.iterrows():
        jira_key = _text(row, "jira_key").upper()
        helix_id = _text(row, "helix_id").upper()
        if not jira_key or not helix_id:
            continue
        rows.append(
            FinalistDiscrepancyIssueRow(
                jira_key=jira_key,
                jira_summary=_text(row, "jira_summary"),
                jira_status=_text(row, "jira_status"),
                jira_priority=_text(row, "jira_priority"),
                jira_assignee=_text(row, "jira_assignee") or "(sin asignar)",
                po_team_leader=_text(row, "po_team_leader"),
                jira_open_days=int(round(float(row.get("__open_days", 0.0) or 0.0))),
                jira_url=_text(row, "jira_url"),
                helix_id=helix_id,
                helix_summary=_text(row, "helix_summary"),
                helix_description=_text(row, "helix_description"),
                helix_status=_text(row, "helix_status"),
                helix_url=_text(row, "helix_url"),
                source_alias=_text(row, "source_alias"),
            )
        )
    return tuple(rows)
