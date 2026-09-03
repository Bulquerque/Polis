from __future__ import annotations

from decimal import Decimal

from ...foundation.enums import OrderClass, OrderType, Side
from .models import PlannedOrder, Quote, TradeEvent
from .policies import ExecutionModelPolicy

BPS = Decimal("10000")


def signed_slippage(side: Side, price: Decimal, bps: Decimal) -> Decimal:
    factor = bps / BPS
    return price * (Decimal("1") + factor) if side == Side.BUY else price * (Decimal("1") - factor)


def simple_quote_fill(
    order: PlannedOrder,
    quote: Quote,
    remaining: Decimal,
    policy: ExecutionModelPolicy,
) -> tuple[Decimal, Decimal] | None:
    leg = order.legs[0]
    available = quote.ask_size if leg.side == Side.BUY else quote.bid_size
    marketable = order.order_type == OrderType.MARKET or (
        order.limit_price is not None and (
            (leg.side == Side.BUY and order.limit_price >= quote.ask_price)
            or (leg.side == Side.SELL and order.limit_price <= quote.bid_price)
        )
    )
    if not marketable:
        return None
    quantity = min(remaining, available)
    if quantity <= 0:
        return None
    base = quote.ask_price if leg.side == Side.BUY else quote.bid_price
    fill_price = signed_slippage(leg.side, base, policy.aggressive_slippage_bps)
    if order.limit_price is not None:
        fill_price = min(fill_price, order.limit_price) if leg.side == Side.BUY else max(fill_price, order.limit_price)
    return quantity, fill_price


def simple_trade_fill(
    order: PlannedOrder,
    trade: TradeEvent,
    remaining: Decimal,
    policy: ExecutionModelPolicy,
) -> tuple[Decimal, Decimal] | None:
    if order.order_type != OrderType.LIMIT or order.limit_price is None:
        return None
    leg = order.legs[0]
    touched = (
        (leg.side == Side.BUY and trade.price <= order.limit_price)
        or (leg.side == Side.SELL and trade.price >= order.limit_price)
    )
    if not touched:
        return None
    available = max(Decimal("0"), trade.quantity - policy.queue_ahead_quantity)
    quantity = min(remaining, available * policy.passive_fill_fraction)
    if quantity <= 0:
        return None
    return quantity, order.limit_price


def combo_fill(
    order: PlannedOrder,
    quotes: dict[tuple[str, str], Quote],
    policy: ExecutionModelPolicy,
) -> tuple[Decimal, dict[str, Decimal]] | None:
    if any((leg.instrument_id, order.venue) not in quotes for leg in order.legs):
        return None
    net = Decimal("0")
    capacity = order.quantity
    prices: dict[str, Decimal] = {}
    for leg in order.legs:
        quote = quotes[(leg.instrument_id, order.venue)]
        price = quote.ask_price if leg.side == Side.BUY else quote.bid_price
        fill_price = signed_slippage(leg.side, price, policy.aggressive_slippage_bps)
        net += (fill_price if leg.side == Side.BUY else -fill_price) * leg.ratio_quantity
        displayed = quote.ask_size if leg.side == Side.BUY else quote.bid_size
        capacity = min(capacity, displayed / leg.ratio_quantity)
        prices[leg.instrument_id] = fill_price
    if order.limit_price is not None:
        is_debit = order.limit_price >= 0
        if (is_debit and net > order.limit_price) or (not is_debit and net < order.limit_price):
            return None
    if capacity < order.quantity:
        return None
    return order.quantity, prices


def allocations_for_fill(order: PlannedOrder, leg_index: int, fill_quantity: Decimal):
    leg = order.legs[leg_index]
    ratio = fill_quantity / leg.quantity
    return tuple(
        allocation.model_copy(update={
            "allocated_target_quantity": allocation.allocated_target_quantity * ratio,
        })
        for allocation in leg.virtual_allocations
    )
