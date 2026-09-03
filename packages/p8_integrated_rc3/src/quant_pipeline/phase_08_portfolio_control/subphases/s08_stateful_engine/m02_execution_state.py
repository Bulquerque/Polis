from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderClass, OrderStatus, Side
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.execution_state import ALLOWED_TRANSITIONS
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import FillEvent, OrderEvent
from .enums import StatefulEventKind
from .errors import LedgerIntegrityError
from .input_models import S8InputBundle
from .state_models import ExecutionStateBundle, OrderStateRecord, TransitionAuditRecord
from .timeline_models import OrderedEventQueue

MODULE_ID = "P8.S8.M02"


def _initial_state(order):
    return OrderStateRecord(
        order_id=order.order_id, as_of_time=order.submit_at, status=OrderStatus.CREATED,
        ordered_quantity=order.quantity, cumulative_filled_quantity=Decimal("0"),
        remaining_quantity=order.quantity, last_sequence=0,
    )


def _apply_order_event(state: OrderStateRecord, event: OrderEvent) -> tuple[OrderStateRecord, TransitionAuditRecord]:
    if event.status_before != state.status:
        raise LedgerIntegrityError(f"status_before mismatch for {event.order_id}")
    if event.status_after not in ALLOWED_TRANSITIONS[state.status]:
        raise LedgerIntegrityError(f"illegal transition {state.status}->{event.status_after}")
    if event.event_sequence != state.last_sequence + 1:
        raise LedgerIntegrityError(f"event sequence gap for {event.order_id}")
    if event.cumulative_filled_quantity < state.cumulative_filled_quantity:
        raise LedgerIntegrityError(f"filled quantity decreased for {event.order_id}")
    if event.cumulative_filled_quantity > state.ordered_quantity:
        raise LedgerIntegrityError(f"overfill in order ledger: {event.order_id}")
    if event.remaining_quantity != state.ordered_quantity - event.cumulative_filled_quantity:
        raise LedgerIntegrityError(f"remaining quantity mismatch: {event.order_id}")
    before_hash = content_sha256(state)
    updated = state.model_copy(update={
        "as_of_time": event.event_time, "status": event.status_after,
        "cumulative_filled_quantity": event.cumulative_filled_quantity,
        "remaining_quantity": event.remaining_quantity, "last_sequence": event.event_sequence,
    })
    audit = TransitionAuditRecord(
        event_id=event.event_id, event_time=event.event_time, order_id=event.order_id,
        before_hash=before_hash, after_hash=content_sha256(updated), idempotent_replay=True,
    )
    return updated, audit


def _validate_fill_allocations(fill: FillEvent) -> None:
    signed = fill.quantity if fill.side == Side.BUY else -fill.quantity
    allocated = sum((x.allocated_target_quantity for x in fill.virtual_allocations), Decimal("0"))
    if allocated != signed:
        raise LedgerIntegrityError(f"fill allocation mismatch: {fill.fill_id}")


def _validate_fill_totals(value: S8InputBundle, states: dict[str, OrderStateRecord], fills: tuple[FillEvent, ...]) -> None:
    by_order: dict[str, list[FillEvent]] = defaultdict(list)
    for fill in fills:
        if fill.order_id not in states:
            raise LedgerIntegrityError(f"orphan fill: {fill.fill_id}")
        _validate_fill_allocations(fill)
        by_order[fill.order_id].append(fill)
    order_by_id = {x.order_id: x for x in value.s7_handoff.s7_result.planned_orders.orders}
    for order_id, state in states.items():
        order = order_by_id[order_id]
        order_fills = by_order.get(order_id, [])
        if order.order_class == OrderClass.SIMPLE:
            physical = sum((x.quantity for x in order_fills), Decimal("0"))
            if physical != state.cumulative_filled_quantity:
                raise LedgerIntegrityError(f"simple fill total mismatch: {order_id}")
            continue
        by_instrument: dict[str, Decimal] = defaultdict(Decimal)
        for fill in order_fills:
            by_instrument[fill.instrument_id] += fill.quantity
        for leg in order.legs:
            expected = state.cumulative_filled_quantity * leg.ratio_quantity
            if by_instrument.get(leg.instrument_id, Decimal("0")) != expected:
                raise LedgerIntegrityError(f"combo leg fill mismatch: {order_id}/{leg.instrument_id}")


def execute(value: S8InputBundle, queue: OrderedEventQueue) -> ExecutionStateBundle:
    planned = value.s7_handoff.s7_result.planned_orders.orders
    states = {x.order_id: _initial_state(x) for x in planned}
    order_events: list[OrderEvent] = []
    fills: list[FillEvent] = []
    audits: list[TransitionAuditRecord] = []
    seen_events: set[str] = set()
    seen_fills: set[str] = set()
    for envelope in queue.events:
        if envelope.kind == StatefulEventKind.ORDER_EVENT:
            event = envelope.payload
            if not isinstance(event, OrderEvent) or event.event_id in seen_events:
                raise LedgerIntegrityError("invalid or duplicate order event")
            if event.order_id not in states:
                raise LedgerIntegrityError(f"unknown order: {event.order_id}")
            seen_events.add(event.event_id)
            states[event.order_id], audit = _apply_order_event(states[event.order_id], event)
            order_events.append(event); audits.append(audit)
        elif envelope.kind == StatefulEventKind.FILL_EVENT:
            fill = envelope.payload
            if not isinstance(fill, FillEvent) or fill.fill_id in seen_fills:
                raise LedgerIntegrityError("invalid or duplicate fill event")
            seen_fills.add(fill.fill_id); fills.append(fill)
    _validate_fill_totals(value, states, tuple(fills))
    final = tuple(states[k] for k in sorted(states))
    payload = {
        "orders": final, "order_events": tuple(order_events), "fills": tuple(fills),
        "transition_audit": tuple(audits), "order_ledger_hash": content_sha256(tuple(order_events)),
        "fill_ledger_hash": content_sha256(tuple(fills)),
    }
    return ExecutionStateBundle(**payload, content_sha256=content_sha256(payload))
