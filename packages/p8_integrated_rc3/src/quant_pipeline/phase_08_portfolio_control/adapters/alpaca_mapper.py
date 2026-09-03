from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..foundation.enums import OrderClass, OrderStatus, OrderType, PositionIntent, SecurityType, Side, TimeInForce
from ..foundation.errors import UnsupportedMappingError
from ..subphases.s07_execution.models import PlannedOrder

_STATUS_MAP = {
    "new": OrderStatus.ACCEPTED,
    "accepted": OrderStatus.ACCEPTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
    "replaced": OrderStatus.REPLACED,
    "rejected": OrderStatus.REJECTED,
}


def map_status(status: str) -> OrderStatus:
    try:
        return _STATUS_MAP[status.lower()]
    except KeyError as exc:
        raise UnsupportedMappingError(f"unsupported Alpaca status: {status}") from exc


def _order_type(value: OrderType) -> str:
    return value.value.lower()


def _tif(value: TimeInForce) -> str:
    return value.value.lower()


def _position_intent(value: PositionIntent) -> str:
    return value.value.lower()


def _side(value: Side) -> str:
    return value.value.lower()


def to_order_payload(order: PlannedOrder) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "client_order_id": order.client_order_id,
        "qty": str(order.quantity),
        "type": _order_type(order.order_type),
        "time_in_force": _tif(order.time_in_force),
    }
    if order.limit_price is not None:
        payload["limit_price"] = str(order.limit_price)
    if order.security_type == SecurityType.OPTION and order.time_in_force != TimeInForce.DAY:
        raise UnsupportedMappingError("Alpaca option orders require DAY time-in-force")
    if order.order_class == OrderClass.MLEG:
        if not 2 <= len(order.legs) <= 4:
            raise UnsupportedMappingError("Alpaca MLeg supports two to four legs")
        if any(leg.ratio_quantity != leg.ratio_quantity.to_integral_value() for leg in order.legs):
            raise UnsupportedMappingError("Alpaca MLeg ratio quantities must be integral")
        payload["order_class"] = "mleg"
        payload["legs"] = [
            {
                "symbol": leg.instrument_id,
                "ratio_qty": str(leg.ratio_quantity),
                "side": _side(leg.side),
                "position_intent": _position_intent(leg.position_intent),
            }
            for leg in order.legs
        ]
        return payload
    leg = order.legs[0]
    payload.update({
        "order_class": "simple",
        "symbol": leg.instrument_id,
        "side": _side(leg.side),
        "position_intent": _position_intent(leg.position_intent),
    })
    return payload
