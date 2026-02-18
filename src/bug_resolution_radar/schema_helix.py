"""Typed schema models for Helix issue payload normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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
