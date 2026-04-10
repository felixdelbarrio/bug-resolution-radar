"""Report generation package."""

from .executive_ppt import ExecutiveReportResult, generate_scope_executive_ppt
from .period_followup_ppt import PeriodFollowupReportResult, generate_country_period_followup_ppt
from .service import (
    PreparedReportContext,
    ReportFilters,
    build_report_filters,
    generate_executive_report_artifact,
    generate_period_followup_report_artifact,
)

__all__ = [
    "ExecutiveReportResult",
    "PeriodFollowupReportResult",
    "PreparedReportContext",
    "ReportFilters",
    "build_report_filters",
    "generate_scope_executive_ppt",
    "generate_country_period_followup_ppt",
    "generate_executive_report_artifact",
    "generate_period_followup_report_artifact",
]
