"""Typed schema models for Jira issue payload normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# -----------------------------
# JIRA
# -----------------------------
class NormalizedIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    summary: str
    status: str
    type: str
    priority: str
    created: Optional[str] = None
    updated: Optional[str] = None
    resolved: Optional[str] = None
    assignee: str = ""
    reporter: str = ""
    labels: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    resolution: str = ""
    resolution_type: str = ""
    url: str = ""
    country: str = ""
    source_type: str = "jira"
    source_alias: str = ""
    source_id: str = ""


class IssuesDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    ingested_at: str = ""
    jira_base_url: str = ""
    query: str = ""
    issues: List[NormalizedIssue] = Field(default_factory=list)

    @staticmethod
    def empty() -> "IssuesDocument":
        return IssuesDocument(
            schema_version="1.0",
            ingested_at=datetime.now(timezone.utc).isoformat(),
            jira_base_url="",
            query="",
            issues=[],
        )


# -----------------------------
# HELIX (Smart IT)
# -----------------------------
class HelixWorkItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    summary: str = ""
    status: str = ""
    status_raw: str = ""
    priority: str = ""
    incident_type: str = ""
    service: str = ""
    impacted_service: str = ""
    assignee: str = ""
    customer_name: str = ""
    sla_status: str = ""
    target_date: Optional[str] = None
    last_modified: Optional[str] = None
    start_datetime: Optional[str] = None
    closed_date: Optional[str] = None
    matrix_service_n1: str = ""
    source_service_n1: str = ""
    url: str = ""
    country: str = ""
    source_alias: str = ""
    source_id: str = ""
    raw_fields: Dict[str, Any] = Field(default_factory=dict)


class HelixDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    ingested_at: str = ""
    helix_base_url: str = ""
    query: str = ""
    items: List[HelixWorkItem] = Field(default_factory=list)

    @staticmethod
    def empty() -> "HelixDocument":
        return HelixDocument(
            schema_version="1.0",
            ingested_at=datetime.now(timezone.utc).isoformat(),
            helix_base_url="",
            query="",
            items=[],
        )
