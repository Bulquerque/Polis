from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import (
    FillEvent, OrderEvent, RuntimeControlCommand,
)
from .accounting_models import AccountEvent
from .enums import StatefulEventKind, StatefulPriority
from .errors import TimelineIntegrityError
from .input_models import S8InputBundle
from .lifecycle_models import LifecycleEvent
from .management_models import ManagementSignal
from .timeline_models import OrderedEventQueue, StatefulEventEnvelope
from .valuation_models import MarkRecord

MODULE_ID = "P8.S8.M01"


def _available_at(payload: object) -> datetime:
    value = getattr(payload, "available_at", None)
    if value is not None:
        return value
    return getattr(payload, "event_time")


def _wrap(payload: object, kind: StatefulEventKind, priority: StatefulPriority, key: str, sequence: int = 0):
    event_time = getattr(payload, "event_time")
    available_at = _available_at(payload)
    apply_at = max(event_time, available_at)
    return StatefulEventEnvelope(
        event_key=key, event_time=event_time, available_at=available_at, apply_at=apply_at,
        priority=priority, kind=kind, payload=payload, source_sequence=sequence,
    )


def _events(value: S8InputBundle) -> list[StatefulEventEnvelope]:
    result: list[StatefulEventEnvelope] = []
    for item in value.s7_handoff.s7_result.execution.order_events:
        result.append(_wrap(item, StatefulEventKind.ORDER_EVENT, StatefulPriority.ORDER_EVENT, f"order:{item.event_id}", item.event_sequence))
    for item in value.s7_handoff.s7_result.execution.fill_events:
        result.append(_wrap(item, StatefulEventKind.FILL_EVENT, StatefulPriority.FILL_EVENT, f"fill:{item.fill_id}"))
    lifecycle_kind = {
        "EXERCISE": StatefulEventKind.EXERCISE,
        "ASSIGNMENT": StatefulEventKind.ASSIGNMENT,
        "EXPIRATION": StatefulEventKind.EXPIRATION,
        "CASH_SETTLEMENT": StatefulEventKind.CASH_SETTLEMENT,
        "SPLIT": StatefulEventKind.CORPORATE_ACTION,
    }
    for item in value.lifecycle_events:
        result.append(_wrap(item, lifecycle_kind[item.event_type.value], StatefulPriority.LIFECYCLE_EVENT, f"lifecycle:{item.event_id}"))
    for item in value.account_events:
        result.append(_wrap(item, StatefulEventKind(item.event_type.value), StatefulPriority.ACCOUNTING_EVENT, f"account:{item.event_id}"))
    for item in value.marks.marks:
        result.append(_wrap(item, StatefulEventKind.MARK, StatefulPriority.MARK_EVENT, f"mark:{item.mark_id}"))
    for item in value.runtime_commands:
        if isinstance(item, RuntimeControlCommand):
            result.append(_wrap(item, StatefulEventKind.RUNTIME_COMMAND, StatefulPriority.SAFETY_COMMAND, f"runtime:{item.command_id}"))
    for item in value.management_signals:
        result.append(_wrap(item, StatefulEventKind.MANAGEMENT_SIGNAL, StatefulPriority.MANAGEMENT_SIGNAL, f"management:{item.signal_id}"))
    return result


def execute(value: S8InputBundle) -> OrderedEventQueue:
    events = _events(value)
    seen: set[str] = set()
    for event in events:
        if event.event_key in seen:
            raise TimelineIntegrityError(f"duplicate event key: {event.event_key}")
        seen.add(event.event_key)
        if event.apply_at > value.valuation_time:
            raise TimelineIntegrityError(f"event unavailable at valuation_time: {event.event_key}")
    ordered = tuple(sorted(events, key=lambda e: (e.apply_at, int(e.priority), e.source_sequence, e.event_key)))
    payload = {"events": ordered}
    return OrderedEventQueue(**payload, content_sha256=content_sha256(payload))
