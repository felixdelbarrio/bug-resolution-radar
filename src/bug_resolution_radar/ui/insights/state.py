"""Shared session-state keys for Insights combo filters."""

from __future__ import annotations

INSIGHTS_VIEW_MODE_KEY = "insights::combo::view_mode"
INSIGHTS_STATUS_KEY = "insights::combo::status_values"
INSIGHTS_PRIORITY_KEY = "insights::combo::priority_values"
INSIGHTS_FUNCTIONALITY_KEY = "insights::combo::functionality_values"
INSIGHTS_STATUS_MANUAL_KEY = "insights::combo::status_manual_override"
INSIGHTS_LAST_VIEW_MODE_KEY = "insights::combo::last_view_mode"
INSIGHTS_VIEW_MODE_WIDGET_KEY = f"{INSIGHTS_VIEW_MODE_KEY}::widget"
INSIGHTS_STATUS_WIDGET_KEY = f"{INSIGHTS_STATUS_KEY}::widget"
INSIGHTS_PRIORITY_WIDGET_KEY = f"{INSIGHTS_PRIORITY_KEY}::widget"
INSIGHTS_FUNCTIONALITY_WIDGET_KEY = f"{INSIGHTS_FUNCTIONALITY_KEY}::widget"
