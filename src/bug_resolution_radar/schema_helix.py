from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class HelixWorkItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    summary: str = ""
    status: str = ""
    priority: str = ""
    assignee: str = ""
    customer_name: str = ""
    target_date: Optional[str] = None
    last_modified: Optional[str] = None
    url: str = ""


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
