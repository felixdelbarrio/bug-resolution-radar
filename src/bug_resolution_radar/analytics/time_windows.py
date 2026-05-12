"""Deterministic quincenal time windows and Spanish range labels."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
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
class QuincenalWindow:
    current_start: pd.Timestamp
    current_end: pd.Timestamp
    previous_start: pd.Timestamp
    previous_end: pd.Timestamp
    month_start: pd.Timestamp

    @property
    def total_start(self) -> pd.Timestamp:
        return self.previous_start

    @property
    def total_end(self) -> pd.Timestamp:
        return self.current_end


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
    ) -> QuincenalWindow:
        anchor = self.normalize_reference_day(reference_day)
        if last_finished_only:
            anchor = self._last_finished_anchor(anchor)
        return self._window_for_anchor(anchor)

    def format_current_created_label(self, window: QuincenalWindow, *, singular: bool) -> str:
        verb = "CREADA" if singular else "CREADAS"
        return f"{verb} DEL {self._same_month_range(window.current_start, window.current_end)}"

    def format_current_closed_label(self, window: QuincenalWindow, *, singular: bool) -> str:
        verb = "CERRADA" if singular else "CERRADAS"
        return f"{verb} DEL {self._same_month_range(window.current_start, window.current_end)}"

    def format_previous_range_label(self, window: QuincenalWindow) -> str:
        return self._full_range(window.previous_start, window.previous_end)

    def format_window_label(self, window: QuincenalWindow) -> str:
        start = window.current_start.strftime("%d/%m")
        end = window.current_end.strftime("%d/%m/%Y")
        return f"Periodo {start} - {end}"

    def _last_finished_anchor(self, anchor: pd.Timestamp) -> pd.Timestamp:
        month_start = anchor.replace(day=1)
        if int(anchor.day) <= 15:
            return month_start - pd.Timedelta(days=1)
        return month_start + pd.Timedelta(days=14)

    def _window_for_anchor(self, anchor: pd.Timestamp) -> QuincenalWindow:
        month_start = anchor.replace(day=1)
        month_end_day = calendar.monthrange(int(anchor.year), int(anchor.month))[1]
        month_end = anchor.replace(day=month_end_day)

        if int(anchor.day) <= 15:
            current_start = month_start
            current_end = month_start + pd.Timedelta(days=14)
        else:
            current_start = month_start + pd.Timedelta(days=15)
            current_end = month_end

        if int(current_start.day) == 1:
            previous_end = current_start - pd.Timedelta(days=1)
            previous_start = previous_end.replace(day=15)
        else:
            previous_start = current_start.replace(day=1)
            previous_end = current_start - pd.Timedelta(days=1)

        return QuincenalWindow(
            current_start=current_start.normalize(),
            current_end=current_end.normalize(),
            previous_start=previous_start.normalize(),
            previous_end=previous_end.normalize(),
            month_start=current_start.replace(day=1).normalize(),
        )

    def _month_abbr(self, value: pd.Timestamp) -> str:
        month = int(pd.Timestamp(value).month)
        return _SPANISH_MONTH_ABBR[month - 1]

    def _same_month_range(self, start: pd.Timestamp, end: pd.Timestamp) -> str:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if int(start_ts.month) == int(end_ts.month) and int(start_ts.year) == int(end_ts.year):
            return f"{start_ts.day:02d} AL {end_ts.day:02d} {self._month_abbr(end_ts)}"
        return f"{self._full_date(start_ts)} AL {self._full_date(end_ts)}"

    def _full_range(self, start: pd.Timestamp, end: pd.Timestamp) -> str:
        return f"{self._full_date(start)} - {self._full_date(end)}"

    def _full_date(self, value: pd.Timestamp) -> str:
        ts = pd.Timestamp(value)
        return f"{ts.day:02d} {self._month_abbr(ts)}"


def default_time_window_service() -> TimeWindowService:
    return TimeWindowService()
