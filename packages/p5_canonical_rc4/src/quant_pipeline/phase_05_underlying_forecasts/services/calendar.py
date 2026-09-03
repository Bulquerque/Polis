"""Trading-session calendar port and deterministic CPU-first implementation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol

from ..errors import DataQualityError
from .identifiers import as_utc


class TradingCalendarPort(Protocol):
    calendar_id: str
    calendar_version: str

    def is_session(self, value: date) -> bool: ...

    def advance_sessions(self, value: datetime, count: int) -> datetime: ...

    def previous_session(self, value: datetime) -> datetime: ...

    def session_close(self, value: date) -> datetime: ...

    def horizon_end(self, value: datetime, horizon: str) -> datetime: ...


@dataclass(frozen=True)
class WeekdayTradingCalendar:
    """Deterministic weekday calendar; explicit holidays can be injected."""

    holidays: frozenset[date] = frozenset()
    calendar_id: str = "WEEKDAY_UTC"
    calendar_version: str = "1.0"
    close_hour_utc: int = 21

    def is_session(self, value: date) -> bool:
        return value.weekday() < 5 and value not in self.holidays

    def session_close(self, value: date) -> datetime:
        if not self.is_session(value):
            raise DataQualityError(f"{value.isoformat()} is not a trading session")
        return datetime.combine(value, time(self.close_hour_utc), tzinfo=timezone.utc)

    def advance_sessions(self, value: datetime, count: int) -> datetime:
        if count < 0:
            raise DataQualityError("session count must be nonnegative")
        current = as_utc(value)
        if count == 0:
            return current
        day = current.date()
        moved = 0
        while moved < count:
            day += timedelta(days=1)
            if self.is_session(day):
                moved += 1
        return datetime.combine(day, current.timetz().replace(tzinfo=timezone.utc))

    def previous_session(self, value: datetime) -> datetime:
        current = as_utc(value)
        day = current.date() - timedelta(days=1)
        while not self.is_session(day):
            day -= timedelta(days=1)
        return datetime.combine(day, current.timetz().replace(tzinfo=timezone.utc))

    def horizon_end(self, value: datetime, horizon: str) -> datetime:
        normalized = str(horizon).strip().upper()
        if normalized.endswith("H"):
            count = int(normalized[:-1])
            return as_utc(value) + timedelta(hours=count)
        if normalized.endswith("D"):
            return self.advance_sessions(value, int(normalized[:-1]))
        if normalized.endswith("W"):
            return self.advance_sessions(value, int(normalized[:-1]) * 5)
        if normalized.endswith("M"):
            return self.advance_sessions(value, int(normalized[:-1]) * 21)
        raise DataQualityError(f"unsupported market horizon: {horizon!r}")


_DEFAULT = WeekdayTradingCalendar()


def default_calendar() -> WeekdayTradingCalendar:
    return _DEFAULT


def horizon_end(value: datetime, horizon: str) -> datetime:
    return _DEFAULT.horizon_end(value, horizon)
