from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

class NormalizedIssue(BaseModel):
    key: str
    summary: str
    status: str
    type: str
    priority: str
    criticality: str
    created: Optional[str] = None
    updated: Optional[str] = None
    resolved: Optional[str] = None
    assignee: str = ""
    reporter: str = ""
    labels: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    affected_clients_count: int = 0
    is_master: bool = False
    resolution: str = ""
    resolution_type: str = ""
    url: str = ""

class IssuesDocument(BaseModel):
    schema_version: str = "1.0"
    ingested_at: str = ""
    jira_base_url: str = ""
    project_key: str = ""
    query: str = ""
    issues: List[NormalizedIssue] = Field(default_factory=list)

    @staticmethod
    def empty() -> "IssuesDocument":
        return IssuesDocument(
            schema_version="1.0",
            ingested_at=datetime.now(timezone.utc).isoformat(),
            jira_base_url="",
            project_key="",
            query="",
            issues=[],
        )
