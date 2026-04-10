"""Unified insight engine for adaptive, filter-aware executive narratives."""

from bug_resolution_radar.analytics.trend_insights import (
    ActionInsight,
    InsightMetric,
    TrendInsightPack,
    build_duplicates_brief,
    build_ops_health_brief,
    build_people_plan_recommendations,
    build_topic_brief,
    build_trend_insight_pack,
    classify_theme,
    theme_counts,
    top_non_other_theme,
)

__all__ = [
    "ActionInsight",
    "InsightMetric",
    "TrendInsightPack",
    "build_duplicates_brief",
    "build_ops_health_brief",
    "build_people_plan_recommendations",
    "build_topic_brief",
    "build_trend_insight_pack",
    "classify_theme",
    "theme_counts",
    "top_non_other_theme",
]
