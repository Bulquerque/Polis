"""Exact terminal payoff, entry cash flow, tail, and break-even calculations."""

from __future__ import annotations

from decimal import Decimal

from .enums import InstrumentType, OptionType, Side
from .models import StrategyLeg

ZERO = Decimal("0")


def side_sign(side: Side) -> Decimal:
    return Decimal("1") if side is Side.LONG else Decimal("-1")


def leg_entry_cash_flow(leg: StrategyLeg) -> Decimal:
    return side_sign(leg.side) * leg.entry_price_reference * leg.quantity * leg.multiplier


def strategy_entry_cash_flow(legs: tuple[StrategyLeg, ...]) -> Decimal:
    return sum((leg_entry_cash_flow(leg) for leg in legs), ZERO)


def leg_terminal_value(leg: StrategyLeg, spot: Decimal) -> Decimal:
    sign = side_sign(leg.side)
    units = leg.quantity * leg.multiplier
    if leg.instrument_type is InstrumentType.UNDERLYING:
        return sign * spot * units
    if leg.instrument_type is InstrumentType.CASH:
        return sign * units
    if leg.strike is None:
        raise ValueError("option leg requires strike")
    if leg.option_type is OptionType.CALL:
        intrinsic = max(spot - leg.strike, ZERO)
    else:
        intrinsic = max(leg.strike - spot, ZERO)
    return sign * intrinsic * units


def strategy_terminal_pnl(
    legs: tuple[StrategyLeg, ...],
    spot: Decimal,
    transaction_cost: Decimal = ZERO,
) -> Decimal:
    terminal = sum((leg_terminal_value(leg, spot) for leg in legs), ZERO)
    return terminal - strategy_entry_cash_flow(legs) - transaction_cost


def right_tail_slope(legs: tuple[StrategyLeg, ...]) -> Decimal:
    slope = ZERO
    for leg in legs:
        sign = side_sign(leg.side)
        units = leg.quantity * leg.multiplier
        if leg.instrument_type is InstrumentType.UNDERLYING:
            slope += sign * units
        elif leg.instrument_type is InstrumentType.OPTION and leg.option_type is OptionType.CALL:
            slope += sign * units
    return slope


def critical_spots(legs: tuple[StrategyLeg, ...], reference_spot: Decimal) -> tuple[Decimal, ...]:
    strikes = {leg.strike for leg in legs if leg.strike is not None}
    points = {ZERO, reference_spot, reference_spot * Decimal("2")}
    points.update(strike for strike in strikes if strike is not None)
    if strikes:
        points.add(max(strikes) * Decimal("3"))
    return tuple(sorted(points))


def break_even_points(spots: tuple[Decimal, ...], pnl: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    roots: list[Decimal] = []
    for left_spot, right_spot, left_value, right_value in zip(spots, spots[1:], pnl, pnl[1:]):
        if left_value == ZERO:
            roots.append(left_spot)
        if left_value * right_value < ZERO:
            weight = -left_value / (right_value - left_value)
            roots.append(left_spot + weight * (right_spot - left_spot))
    if pnl and pnl[-1] == ZERO:
        roots.append(spots[-1])
    return tuple(sorted(set(roots)))
