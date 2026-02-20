from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.insights import build_chart_insights


def test_open_status_insights_treats_accepted_as_final_stage() -> None:
    now = pd.Timestamp.utcnow().tz_localize(None)
    open_df = pd.DataFrame(
        {
            "status": [
                "Accepted",
                "Accepted",
                "Accepted",
                "Accepted",
                "Ready to deploy",
                "Deployed",
            ],
            "created": pd.to_datetime(
                [
                    now - pd.Timedelta(days=24),
                    now - pd.Timedelta(days=20),
                    now - pd.Timedelta(days=18),
                    now - pd.Timedelta(days=15),
                    now - pd.Timedelta(days=8),
                    now - pd.Timedelta(days=5),
                ],
                utc=True,
            ),
        }
    )

    insights = build_chart_insights("open_status_bar", dff=pd.DataFrame(), open_df=open_df)
    titles = [str(i.title or "").lower() for i in insights]
    bodies = " ".join([str(i.body or "").lower() for i in insights])

    assert not any("cuello de botella" in t for t in titles)
    assert "no se interpreta como cuello" in bodies
    assert "accepted" in bodies and "ready to deploy" in bodies
