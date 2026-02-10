from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bug_resolution_radar.config import Settings
from bug_resolution_radar.kpis import compute_kpis


def test_kpis_basic_counts() -> None:
    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Bug 1",
                "status": "Open",
                "type": "Bug",
                "priority": "Highest",
                "created": now - timedelta(days=2),
                "updated": now - timedelta(days=1),
                "resolved": pd.NaT,
                "resolution_type": "",
                "assignee": "Alice",
                "components": [],
                "labels": [],
            },
            {
                "key": "A-2",
                "summary": "Bug 2",
                "status": "Closed",
                "type": "Bug",
                "priority": "High",
                "created": now - timedelta(days=10),
                "updated": now - timedelta(days=1),
                "resolved": now - timedelta(days=1),
                "resolution_type": "Done",
                "assignee": "Bob",
                "components": [],
                "labels": [],
            },
        ]
    )
    settings = Settings(
        KPI_FORTNIGHT_DAYS="15",
        KPI_MONTH_DAYS="30",
        KPI_OPEN_AGE_X_DAYS="7,14,30",
        KPI_AGE_BUCKETS="0-2,3-7,8-14,15-30,>30",
    )
    k = compute_kpis(df, settings=settings)
    assert k["open_now_total"] == 1
    assert k["new_fortnight_total"] == 2
    assert k["closed_fortnight_total"] == 1
    assert k["mean_resolution_days"] > 0
