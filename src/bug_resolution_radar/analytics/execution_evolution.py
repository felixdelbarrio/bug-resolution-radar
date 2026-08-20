"""Authoritative year and fortnight execution evolution for every delivery channel."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from bug_resolution_radar.analytics.issues import critical_priority_mask, normalize_text_col
from bug_resolution_radar.analytics.quincenal_calculators import NormalizedIssueFrame
from bug_resolution_radar.analytics.time_windows import ReportingWindow, TimeWindowService


@dataclass(frozen=True)
class _FlowMetrics:
    start: date
    end: date
    backlog_start: int
    backlog_end: int
    created: int
    closed: int
    resolution_days: float | None
    average_open: float
    critical_end: int
    aged30_end: int

    @property
    def backlog_delta(self) -> int:
        return self.backlog_end - self.backlog_start

    @property
    def net_flow(self) -> int:
        return self.created - self.closed


def _reference_day(frame: pd.DataFrame, explicit: pd.Timestamp | str | None) -> pd.Timestamp:
    if explicit is not None:
        parsed = pd.to_datetime(explicit, errors="coerce", utc=True)
        if pd.notna(parsed):
            return pd.Timestamp(parsed).tz_convert(None).normalize()
    candidates: list[pd.Timestamp] = []
    for column in ("updated", "resolved", "created"):
        if column not in frame.columns:
            continue
        values = pd.to_datetime(frame[column], errors="coerce", utc=True)
        if values.notna().any():
            candidates.append(pd.Timestamp(values.max()).tz_convert(None).normalize())
    return max(candidates) if candidates else pd.Timestamp.now("UTC").tz_localize(None).normalize()


def _between(values: pd.Series, start: date, end: date) -> pd.Series:
    return (
        values.dt.normalize()
        .between(pd.Timestamp(start), pd.Timestamp(end), inclusive="both")
        .fillna(False)
    )


def _open_mask(frame: NormalizedIssueFrame, day: date) -> pd.Series:
    cutoff = pd.Timestamp(day)
    return (
        frame.created_at.notna()
        & frame.created_at.dt.normalize().le(cutoff)
        & (frame.finalized_at.isna() | frame.finalized_at.dt.normalize().gt(cutoff))
    ).fillna(False)


def _flow_metrics(
    frame: NormalizedIssueFrame,
    *,
    start: date,
    end: date,
    critical_mask: pd.Series,
) -> _FlowMetrics:
    created_mask = _between(frame.created_at, start, end)
    closed_mask = _between(frame.finalized_at, start, end)
    start_open = _open_mask(frame, (pd.Timestamp(start) - pd.Timedelta(days=1)).date())
    end_open = _open_mask(frame, end)
    resolution_days = (frame.resolved_at - frame.created_at).dt.total_seconds() / 86400.0
    resolved_mask = _between(frame.resolved_at, start, end) & resolution_days.ge(0).fillna(False)
    resolved_values = resolution_days.loc[resolved_mask].dropna()
    period_end = pd.Timestamp(end)
    period_days = (end - start).days + 1
    created_open_days = (
        (period_end - frame.created_at.loc[created_mask].dt.normalize()).dt.days.add(1).sum()
    )
    finalized_open_days = (
        (period_end - frame.finalized_at.loc[closed_mask].dt.normalize()).dt.days.add(1).sum()
    )
    total_open_days = (
        int(start_open.sum()) * period_days + int(created_open_days) - int(finalized_open_days)
    )
    end_created = frame.created_at.loc[end_open]
    end_age = (pd.Timestamp(end) - end_created.dt.normalize()).dt.days
    return _FlowMetrics(
        start=start,
        end=end,
        backlog_start=int(start_open.sum()),
        backlog_end=int(end_open.sum()),
        created=int(created_mask.sum()),
        closed=int(closed_mask.sum()),
        resolution_days=float(resolved_values.mean()) if not resolved_values.empty else None,
        average_open=max(float(total_open_days) / float(period_days), 0.0),
        critical_end=int((end_open & critical_mask).sum()),
        aged30_end=int((end_age > 30).sum()),
    )


def _tone(delta: float, *, lower_is_better: bool = True) -> str:
    if delta == 0:
        return "neutral"
    improves = delta < 0 if lower_is_better else delta > 0
    return "positive" if improves else "negative"


def _metric(
    metric_id: str,
    label: str,
    current: int | float | None,
    previous: int | float | None,
    *,
    unit: str = "count",
    lower_is_better: bool = True,
) -> dict[str, Any]:
    delta = None if current is None or previous is None else float(current) - float(previous)
    return {
        "id": metric_id,
        "label": label,
        "current": current,
        "previous": previous,
        "delta": delta,
        "unit": unit,
        "tone": _tone(delta, lower_is_better=lower_is_better) if delta is not None else "neutral",
    }


def _window_label(service: TimeWindowService, metrics: _FlowMetrics) -> str:
    return service.format_compact_range(metrics.start, metrics.end)


def _decimal_es(value: float) -> str:
    return f"{float(value):.1f}".replace(".", ",")


def _resolution_comparison(current: _FlowMetrics, previous: _FlowMetrics) -> str:
    if current.resolution_days is None or previous.resolution_days is None:
        return ""
    delta = current.resolution_days - previous.resolution_days
    current_txt = _decimal_es(current.resolution_days)
    previous_txt = _decimal_es(previous.resolution_days)
    if abs(delta) < 0.05:
        return f"El tiempo medio de resolución se mantiene en {current_txt} días."
    movement = "mejora: baja" if delta < 0 else "empeora: sube"
    return (
        f"El tiempo medio de resolución {movement} {_decimal_es(abs(delta))} días, "
        f"de {previous_txt} a {current_txt}."
    )


def _portfolio_comparison(current: _FlowMetrics, previous: _FlowMetrics) -> str:
    delta = current.average_open - previous.average_open
    current_txt = _decimal_es(current.average_open)
    previous_txt = _decimal_es(previous.average_open)
    if abs(delta) < 0.05:
        movement = f"se mantiene en {current_txt} incidencias"
    else:
        verb = "baja" if delta < 0 else "sube"
        movement = (
            f"{verb} {_decimal_es(abs(delta))} incidencias, de {previous_txt} a {current_txt}"
        )
    return f"La cartera abierta media {movement} y cierra en {current.backlog_end}."


def _fortnight_ranges(year: int, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    for month in range(1, end.month + 1):
        last = monthrange(year, month)[1]
        for start_day, end_day in ((1, 14), (15, last)):
            start = date(year, month, start_day)
            if start > end:
                break
            ranges.append((start, min(date(year, month, end_day), end)))
    return ranges


def _executive_message(
    *,
    annual: _FlowMetrics,
    current: _FlowMetrics,
    previous: _FlowMetrics,
) -> tuple[str, str, str]:
    if annual.created == 0 and annual.backlog_start == 0 and annual.backlog_end == 0:
        return (
            "neutral",
            "Sin datos para evaluar la evolución",
            "El ámbito seleccionado no contiene incidencias con las que calcular una evolución fiable.",
        )
    period_delta = current.backlog_delta
    annual_delta = annual.backlog_delta
    if period_delta < 0 and current.closed >= current.created:
        tone = "positive"
        title = f"Backlog reducido en {abs(period_delta)} durante la quincena"
    elif period_delta > 0 and current.created > current.closed:
        tone = "negative"
        title = f"Backlog incrementado en {period_delta} durante la quincena"
    elif period_delta == 0:
        tone = "neutral"
        title = "Backlog estable durante la quincena"
    else:
        tone = "mixed"
        title = "Evolución mixta durante la quincena"
    annual_direction = (
        f"disminuye en {abs(annual_delta)}"
        if annual_delta < 0
        else f"aumenta en {annual_delta}"
        if annual_delta > 0
        else "se mantiene estable"
    )
    summary = (
        f"Se cerraron {current.closed} incidencias y se crearon {current.created}; "
        f"el backlog pasa de {current.backlog_start} a {current.backlog_end}. "
        f"{_portfolio_comparison(current, previous)} "
    )
    resolution_comparison = _resolution_comparison(current, previous)
    if resolution_comparison:
        summary += f"{resolution_comparison} "
    summary += f"En el año, {annual_direction}, de {annual.backlog_start} a {annual.backlog_end}."
    if current.critical_end:
        summary += f" Permanecen {current.critical_end} incidencias de criticidad alta o muy alta."
    else:
        summary += " No hay incidencias abiertas de criticidad alta o muy alta."
    return tone, title, summary


def _focus_lines(
    *,
    current: _FlowMetrics,
    previous: _FlowMetrics,
) -> list[str]:
    lines: list[str] = []
    if current.critical_end > 0:
        delta = current.critical_end - previous.critical_end
        lines.append(
            f"Criticidad: {current.critical_end} abiertas al cierre ({delta:+d} vs quincena previa)."
        )
    if current.aged30_end > 0:
        delta = current.aged30_end - previous.aged30_end
        lines.append(
            f"Antigüedad: {current.aged30_end} abiertas superan 30 días ({delta:+d} vs quincena previa)."
        )
    if current.created > current.closed:
        lines.append(
            f"Capacidad: entraron {current.created - current.closed} incidencias más de las que se cerraron."
        )
    if (
        current.resolution_days is not None
        and previous.resolution_days is not None
        and current.resolution_days > previous.resolution_days
    ):
        lines.append(
            "Resolución: el tiempo medio sube "
            f"{current.resolution_days - previous.resolution_days:.1f} días frente a la quincena previa."
        )
    return lines[:3]


def build_execution_evolution(
    *,
    dff: pd.DataFrame,
    reference_day: pd.Timestamp | str | None = None,
    last_finished_only: bool = False,
) -> dict[str, Any]:
    """Build one evidence-backed evolution contract for UI, export and newsletter."""
    safe = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    ref = _reference_day(safe, reference_day)
    service = TimeWindowService()
    window: ReportingWindow = service.current_window(ref, last_finished_only=last_finished_only)
    normalized = NormalizedIssueFrame.from_df(safe)
    priorities = (
        normalize_text_col(safe["priority"], "(sin prioridad)")
        if "priority" in safe.columns
        else pd.Series("", index=safe.index, dtype=str)
    )
    critical = critical_priority_mask(priorities)
    current = _flow_metrics(
        normalized,
        start=window.current_start,
        end=window.current_end,
        critical_mask=critical,
    )
    previous = _flow_metrics(
        normalized,
        start=window.previous_start,
        end=window.previous_end,
        critical_mask=critical,
    )
    annual = _flow_metrics(
        normalized,
        start=date(ref.year, 1, 1),
        end=ref.date(),
        critical_mask=critical,
    )
    has_data = bool(annual.created or annual.backlog_start or annual.backlog_end)
    timeline = [
        _flow_metrics(normalized, start=start, end=end, critical_mask=critical)
        for start, end in _fortnight_ranges(ref.year, ref.date())
    ]
    tone, title, summary = _executive_message(
        annual=annual,
        current=current,
        previous=previous,
    )
    focus = _focus_lines(current=current, previous=previous)

    def flow_payload(metrics: _FlowMetrics) -> dict[str, Any]:
        return {
            "label": _window_label(service, metrics),
            "start": metrics.start.isoformat(),
            "end": metrics.end.isoformat(),
            "backlogStart": metrics.backlog_start,
            "backlogEnd": metrics.backlog_end,
            "backlogDelta": metrics.backlog_delta,
            "created": metrics.created,
            "closed": metrics.closed,
            "netFlow": metrics.net_flow,
            "resolutionDays": round(metrics.resolution_days, 1)
            if metrics.resolution_days is not None
            else None,
            "averageOpen": round(metrics.average_open, 1),
            "criticalOpen": metrics.critical_end,
            "aged30Open": metrics.aged30_end,
        }

    return {
        "hasData": has_data,
        "referenceDate": ref.date().isoformat(),
        "year": int(ref.year),
        "executive": {
            "tone": tone,
            "title": title,
            "summary": summary,
            "focus": focus,
        },
        "annual": {
            **flow_payload(annual),
            "label": f"Evolución {ref.year}",
            "kpis": [
                _metric("backlog", "Backlog", annual.backlog_end, annual.backlog_start),
                _metric("created", "Creadas", annual.created, None),
                _metric("closed", "Cerradas", annual.closed, None),
                _metric("critical", "Criticidad alta", annual.critical_end, None),
            ],
        },
        "fortnight": {
            "current": flow_payload(current),
            "previous": flow_payload(previous),
            "kpis": [
                _metric("backlog", "Backlog al cierre", current.backlog_end, previous.backlog_end),
                _metric(
                    "averageOpen",
                    "Cartera abierta media",
                    round(current.average_open, 1),
                    round(previous.average_open, 1),
                    unit="average",
                ),
                _metric("created", "Creadas", current.created, previous.created),
                _metric(
                    "closed", "Cerradas", current.closed, previous.closed, lower_is_better=False
                ),
                _metric(
                    "resolution",
                    "Resolución media",
                    round(current.resolution_days, 1)
                    if current.resolution_days is not None
                    else None,
                    round(previous.resolution_days, 1)
                    if previous.resolution_days is not None
                    else None,
                    unit="days",
                ),
                _metric("critical", "Criticidad alta", current.critical_end, previous.critical_end),
                _metric("aged30", "Abiertas >30 días", current.aged30_end, previous.aged30_end),
            ],
        },
        "period": {
            **flow_payload(current),
            "summary": summary,
            "focus": focus,
        },
        "timeline": [flow_payload(metrics) for metrics in timeline] if has_data else [],
        "learningMeasurement": {
            "reference_date": ref.date().isoformat(),
            "open_total": current.backlog_end,
            "average_open_14": round(current.average_open, 1),
            "resolution_days_14": round(current.resolution_days, 1)
            if current.resolution_days is not None
            else None,
            "aged30_count": current.aged30_end,
            "critical_count": current.critical_end,
            "created_14": current.created,
            "resolved_14": current.closed,
            "net_14": current.net_flow,
            "year_open_start": annual.backlog_start,
            "year_created": annual.created,
            "year_closed": annual.closed,
        },
    }
