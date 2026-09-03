from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ...foundation.enums import OrderEventType, OrderStatus
from ...foundation.errors import StateTransitionError
from ...foundation.hashing import deterministic_id
from .models import OrderEvent, PlannedOrder


@dataclass
class OrderExecutionState:
    order: PlannedOrder
    status: OrderStatus = OrderStatus.CREATED
    filled: Decimal = Decimal("0")
    sequence: int = 0

    @property
    def remaining(self) -> Decimal:
        return self.order.quantity - self.filled


ALLOWED_TRANSITIONS = {
    OrderStatus.CREATED: {OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.SUBMITTED: {OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.ACCEPTED: {
        OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED,
        OrderStatus.EXPIRED, OrderStatus.REPLACED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED,
        OrderStatus.EXPIRED, OrderStatus.REPLACED,
    },
    OrderStatus.REPLACED: {OrderStatus.ACCEPTED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.EXPIRED: set(),
}
TERMINAL_ORDER_STATUSES = {
    OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED,
}


def emit_order_event(
    state: OrderExecutionState,
    new_status: OrderStatus,
    event_type: OrderEventType,
    at: datetime,
    reason: str,
) -> OrderEvent:
    if new_status not in ALLOWED_TRANSITIONS[state.status]:
        raise StateTransitionError(f"illegal transition {state.status} -> {new_status}")
    before = state.status
    state.status = new_status
    state.sequence += 1
    return OrderEvent(
        event_id=deterministic_id("order-event", state.order.order_id, state.sequence, new_status, at),
        order_id=state.order.order_id,
        event_type=event_type,
        event_time=at,
        status_before=before,
        status_after=new_status,
        cumulative_filled_quantity=state.filled,
        remaining_quantity=state.remaining,
        reason_code=reason,
        event_sequence=state.sequence,
    )
