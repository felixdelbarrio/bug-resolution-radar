"""Deterministic quincenal time windows and Spanish range labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

DEFAULT_QUINCENAL_TIMEZONE = "UTC"
DEFAULT_QUINCENAL_LOCALE = "es"

_SPANISH_MONTH_ABBR: tuple[str, ...] = (
    "ENE",
    "FEB",
    "MAR",
    "ABR",
    "MAY",
    "JUN",
    "JUL",
    "AGO",
    "SEP",
    "OCT",
    "NOV",
    "DIC",
)


@dataclass(frozen=True)
class ReportingWindow:
    reference_date: date
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    use_last_completed_fortnight: bool

    @property
    def month_start(self) -> date:
        return self.current_start.replace(day=1)

    @property
    def total_start(self) -> date:
        return self.previous_start

    @property
    def total_end(self) -> date:
        return self.current_end


QuincenalWindow = ReportingWindow


class TimeWindowService:
    """Single source of truth for fortnight windows used by reports and UI."""

    def __init__(
        self,
        *,
        timezone_name: str = DEFAULT_QUINCENAL_TIMEZONE,
        locale: str = DEFAULT_QUINCENAL_LOCALE,
    ) -> None:
        self.timezone_name = str(timezone_name or DEFAULT_QUINCENAL_TIMEZONE).strip()
        self.locale = str(locale or DEFAULT_QUINCENAL_LOCALE).strip() or DEFAULT_QUINCENAL_LOCALE
        try:
            self._timezone = ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError:
            self.timezone_name = DEFAULT_QUINCENAL_TIMEZONE
            self._timezone = ZoneInfo(DEFAULT_QUINCENAL_TIMEZONE)

    def normalize_reference_day(self, reference_day: pd.Timestamp | str) -> pd.Timestamp:
        ts = pd.Timestamp(reference_day)
        if pd.isna(ts):
            raise ValueError("reference_day must be a valid timestamp")
        if ts.tzinfo is None:
            localized = ts.tz_localize(self._timezone)
        else:
            localized = ts.tz_convert(self._timezone)
        return localized.normalize().tz_localize(None)

    def today(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz=self._timezone).normalize().tz_localize(None)

    def current_window(
        self,
        reference_day: pd.Timestamp | str,
        *,
        last_finished_only: bool = False,
    ) -> ReportingWindow:
        reference = self.normalize_reference_day(reference_day).date()
        if last_finished_only:
            current_start, current_end = self._completed_window_before(reference)
        else:
            current_start, current_end = self._active_window(reference)
        previous_start, previous_end = self._completed_window_before(current_start)
        return ReportingWindow(
            reference_date=reference,
            current_start=current_start,
            current_end=current_end,
            previous_start=previous_start,
            previous_end=previous_end,
            use_last_completed_fortnight=bool(last_finished_only),
        )

    def format_current_created_label(self, window: ReportingWindow, *, singular: bool) -> str:
        verb = "CREADA" if singular else "CREADAS"
        return (
            f"{verb} DEL {self._same_month_range_words(window.current_start, window.current_end)}"
        )

    def format_current_closed_label(self, window: ReportingWindow, *, singular: bool) -> str:
        verb = "CERRADA" if singular else "CERRADAS"
        return f"{verb} DEL {self.format_compact_range(window.current_start, window.current_end)}"

    def format_previous_range_label(self, window: ReportingWindow) -> str:
        return self.format_compact_range(window.previous_start, window.previous_end)

    def format_window_label(self, window: ReportingWindow) -> str:
        start = pd.Timestamp(window.current_start).strftime("%d/%m")
        end = pd.Timestamp(window.current_end).strftime("%d/%m/%Y")
        return f"Periodo {start} - {end}"

    def _active_window(self, reference: date) -> tuple[date, date]:
        if int(reference.day) <= 14:
            return reference.replace(day=1), reference
        return reference.replace(day=15), reference

    def _completed_window_before(self, reference: date) -> tuple[date, date]:
        day = int(reference.day)
        if day <= 14:
            end = reference.replace(day=1) - timedelta(days=1)
            return end.replace(day=15), end

        start = reference.replace(day=1)
        return start, start.replace(day=14)

    def _month_abbr(self, value: date | pd.Timestamp) -> str:
        month = int(pd.Timestamp(value).month)
        return _SPANISH_MONTH_ABBR[month - 1]

    def _same_month_range_words(self, start: date, end: date) -> str:
        if int(start.month) == int(end.month) and int(start.year) == int(end.year):
            return f"{start.day:02d} AL {end.day:02d} {self._month_abbr(end)}"
        return f"{self._full_date(start)} AL {self._full_date(end)}"

    def format_compact_range(self, start: date | pd.Timestamp, end: date | pd.Timestamp) -> str:
        start_date = pd.Timestamp(start).date()
        end_date = pd.Timestamp(end).date()
        if int(start_date.month) == int(end_date.month) and int(start_date.year) == int(
            end_date.year
        ):
            return f"{start_date.day:02d}-{end_date.day:02d} {self._month_abbr(end_date)}"
        return f"{self._full_date(start_date)}-{self._full_date(end_date)}"

    def _full_date(self, value: date | pd.Timestamp) -> str:
        ts = pd.Timestamp(value)
        return f"{ts.day:02d} {self._month_abbr(ts)}"


def default_time_window_service() -> TimeWindowService:
    return TimeWindowService()
