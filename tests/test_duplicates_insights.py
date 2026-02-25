from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.insights import SimilarityCluster
from bug_resolution_radar.ui.insights.duplicates import (
    _dedupe_heuristic_clusters,
    _prepare_duplicates_payload,
)


def test_dedupe_heuristic_clusters_prefers_exact_title_groups() -> None:
    clusters = [
        SimilarityCluster(
            size=2,
            summary="Error login token softoken mobile",
            keys=["MX-1", "MX-2"],
            priorities=["High", "High"],
            statuses=["New", "New"],
        ),
        SimilarityCluster(
            size=2,
            summary="Error login token softoken mobile",
            keys=["MX-1", "MX-3"],
            priorities=["High", "Medium"],
            statuses=["New", "Blocked"],
        ),
    ]
    exact_title_groups = {
        "Error login token softoken mobile": ["MX-1", "MX-2"],
    }

    deduped = _dedupe_heuristic_clusters(
        clusters=clusters,
        exact_title_groups=exact_title_groups,
    )

    assert len(deduped) == 1
    assert set(deduped[0].keys) == {"MX-1", "MX-3"}


def test_prepare_duplicates_payload_drops_redundant_heuristic_cluster() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "MX-1",
                "summary": "Error login token softoken mobile",
                "status": "New",
                "priority": "High",
            },
            {
                "key": "MX-2",
                "summary": "Error login token softoken mobile",
                "status": "New",
                "priority": "High",
            },
            {
                "key": "MX-3",
                "summary": "Timeout en transferencias SPEI",
                "status": "Blocked",
                "priority": "Highest",
            },
        ]
    )

    payload = _prepare_duplicates_payload(df)

    top_titles = payload.get("top_titles") or []
    clusters = payload.get("clusters") or []
    heur_export = payload.get("heur_export")

    assert len(top_titles) == 1
    assert top_titles[0][0] == "Error login token softoken mobile"
    assert len(clusters) == 0
    assert heur_export is not None
    assert heur_export.empty
