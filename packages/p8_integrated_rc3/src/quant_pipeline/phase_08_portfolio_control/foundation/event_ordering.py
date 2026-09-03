from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Generic, TypeVar

from .errors import TemporalIntegrityError

PayloadT = TypeVar("PayloadT")


class TimelinePriority(IntEnum):
    SAFETY_COMMAND = 10
    VENUE_STATUS = 20
    ORDER_SUBMISSION = 30
    MARKET_DATA = 40
    ORDER_EXPIRATION = 90


@dataclass(frozen=True, slots=True)
class ScheduledEvent(Generic[PayloadT]):
    available_at: datetime
    priority: TimelinePriority
    event_key: str
    payload: PayloadT


def order_timeline(events: list[ScheduledEvent[PayloadT]]) -> tuple[ScheduledEvent[PayloadT], ...]:
    seen: set[str] = set()
    for event in events:
        if event.available_at.tzinfo is None or event.available_at.utcoffset() is None:
            raise TemporalIntegrityError(f"timeline event is not timezone-aware: {event.event_key}")
        if event.event_key in seen:
            raise TemporalIntegrityError(f"duplicate timeline event key: {event.event_key}")
        seen.add(event.event_key)
    return tuple(sorted(events, key=lambda item: (item.available_at, int(item.priority), item.event_key)))
