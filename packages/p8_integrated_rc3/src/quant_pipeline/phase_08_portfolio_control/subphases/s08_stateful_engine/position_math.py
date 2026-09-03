from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .enums import PositionTransitionType
from .errors import PositionIntegrityError


@dataclass
class MutablePosition:
    quantity: Decimal
    signed_cost_basis: Decimal
    average_entry_price: Decimal | None
    opened_at: datetime | None
    realized_pnl: Decimal


def _sign(value: Decimal) -> Decimal:
    return Decimal("1") if value > 0 else Decimal("-1") if value < 0 else Decimal("0")


def _transition_type(q0: Decimal, q1: Decimal) -> PositionTransitionType:
    if q0 == 0 and q1 != 0: return PositionTransitionType.OPEN
    if q1 == 0: return PositionTransitionType.CLOSE
    if _sign(q0) == _sign(q1) and abs(q1) > abs(q0): return PositionTransitionType.INCREASE
    if _sign(q0) == _sign(q1): return PositionTransitionType.REDUCE
    return PositionTransitionType.REVERSE


def apply_trade(
    state: MutablePosition, signed_quantity_delta: Decimal, price: Decimal,
    multiplier: Decimal, event_time: datetime, allow_reversal: bool = False,
) -> tuple[MutablePosition, Decimal, Decimal, PositionTransitionType]:
    if price < 0 or multiplier <= 0 or signed_quantity_delta == 0:
        raise PositionIntegrityError("invalid trade inputs")
    q0 = state.quantity; q1 = q0 + signed_quantity_delta
    if q0 != 0 and q1 != 0 and _sign(q0) != _sign(q1) and not allow_reversal:
        raise PositionIntegrityError("position reversal is not allowed in one transition")
    realized = Decimal("0")
    if q0 == 0 or _sign(q0) == _sign(signed_quantity_delta):
        basis1 = state.signed_cost_basis + signed_quantity_delta * price * multiplier
        avg1 = abs(basis1) / (abs(q1) * multiplier) if q1 else None
        opened = state.opened_at or event_time
    else:
        close_qty = min(abs(q0), abs(signed_quantity_delta))
        avg0 = state.average_entry_price
        if avg0 is None:
            raise PositionIntegrityError("open position missing average_entry_price")
        realized = (price - avg0) * close_qty * multiplier * _sign(q0)
        if q1 == 0:
            basis1 = Decimal("0"); avg1 = None; opened = None
        elif _sign(q1) == _sign(q0):
            basis1 = _sign(q1) * avg0 * abs(q1) * multiplier
            avg1 = avg0; opened = state.opened_at
        else:
            basis1 = q1 * price * multiplier
            avg1 = price; opened = event_time
    updated = MutablePosition(q1, basis1, avg1, opened, state.realized_pnl + realized)
    cash_delta = -signed_quantity_delta * price * multiplier
    return updated, realized, cash_delta, _transition_type(q0, q1)
