"""Report generation package."""

from .executive_ppt import ExecutiveReportResult, generate_scope_executive_ppt
from .period_followup_ppt import PeriodFollowupReportResult, generate_country_period_followup_ppt

__all__ = [
    "ExecutiveReportResult",
    "PeriodFollowupReportResult",
    "generate_scope_executive_ppt",
    "generate_country_period_followup_ppt",
]
