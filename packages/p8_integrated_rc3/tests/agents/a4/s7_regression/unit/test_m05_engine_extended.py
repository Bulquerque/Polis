from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.agents.a4.conftest import NOW
from quant_pipeline.phase_08_portfolio_control.foundation.enums import (
    OrderStatus,
    OrderType,
    RuntimeControlMode,
    TimeInForce,
    VenueState,
)
from quant_pipeline.phase_08_portfolio_control.foundation.errors import StateTransitionError
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import (
    m01_intents,
    m02_structure,
    m03_routing,
    m05_engine,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import (
    CancelOrderCommand,
    QuoteEvent,
    ReplaceOrderCommand,
    RuntimeControlCommand,
    TradeEvent,
    VenueStatusEvent,
)


def _orders(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents = m01_intents.execute(stock_bundle, context, policies.intent)
    structures = m02_structure.execute(intents, stock_bundle, venue_capabilities, policies.structure)
    return m03_routing.execute(
        intents, structures, stock_bundle, stock_market, venue_capabilities, context, policies.routing
    )


def _single_order(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _orders(stock_bundle, stock_market, context, venue_capabilities, policies)
    return orders.model_copy(update={"orders": (orders.orders[0],)})


def test_fok_cancels_without_partial_fill(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    order = orders.orders[0].model_copy(update={"quantity": Decimal("10"), "time_in_force": TimeInForce.FOK})
    orders = orders.model_copy(update={"orders": (order,)})
    result = m05_engine.execute(orders, (stock_events[0],), (), stock_bundle, context, policies.execution)
    assert result.final_status_by_order[order.order_id] == OrderStatus.CANCELLED
    assert result.fill_events == ()


def test_fok_fills_when_full_size_available(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    order = orders.orders[0].model_copy(update={"quantity": Decimal("6"), "time_in_force": TimeInForce.FOK})
    orders = orders.model_copy(update={"orders": (order,)})
    result = m05_engine.execute(orders, (stock_events[0],), (), stock_bundle, context, policies.execution)
    assert result.final_status_by_order[order.order_id] == OrderStatus.FILLED
    assert result.fill_events[0].quantity == Decimal("6")


def test_passive_limit_fills_on_trade_after_queue(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    order = orders.orders[0].model_copy(update={"limit_price": Decimal("99")})
    orders = orders.model_copy(update={"orders": (order,)})
    trade = TradeEvent(
        event_id="trade-1", event_time=NOW + timedelta(seconds=1), available_at=NOW + timedelta(seconds=1),
        instrument_id="AAPL", price=Decimal("98.5"), quantity=Decimal("10"), venue="SIM",
    )
    policy = policies.execution.model_copy(update={"queue_ahead_quantity": Decimal("1"), "passive_fill_fraction": Decimal("0.5")})
    result = m05_engine.execute(orders, (trade,), (), stock_bundle, context, policy)
    assert result.final_status_by_order[order.order_id] == OrderStatus.EXPIRED
    assert any(event.status_after == OrderStatus.PARTIALLY_FILLED for event in result.order_events)
    assert result.fill_events[0].quantity == Decimal("4.5")
    assert result.fill_events[0].price == Decimal("99")


def test_market_order_branch(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    order = orders.orders[0].model_copy(update={"order_type": OrderType.MARKET, "limit_price": None})
    orders = orders.model_copy(update={"orders": (order,)})
    result = m05_engine.execute(orders, (stock_events[0],), (), stock_bundle, context, policies.execution)
    assert result.fill_events
    assert result.fill_events[0].price == Decimal("101")


def test_venue_closed_before_submission_rejects(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    closed = VenueStatusEvent(
        event_id="closed", event_time=NOW - timedelta(seconds=1), available_at=NOW - timedelta(seconds=1),
        venue="SIM", state=VenueState.CLOSED,
    )
    result = m05_engine.execute(orders, (closed,), (), stock_bundle, context, policies.execution)
    assert set(result.final_status_by_order.values()) == {OrderStatus.REJECTED}


def test_order_expires_without_liquidity(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    result = m05_engine.execute(orders, (), (), stock_bundle, context, policies.execution)
    assert set(result.final_status_by_order.values()) == {OrderStatus.EXPIRED}


def test_cancel_specific_order(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    order = orders.orders[0]
    command = CancelOrderCommand(
        command_id="cancel", event_time=NOW + timedelta(milliseconds=1), order_id=order.order_id,
        reason_code="USER_CANCEL",
    )
    result = m05_engine.execute(orders, (), (command,), stock_bundle, context, policies.execution)
    assert result.final_status_by_order[order.order_id] == OrderStatus.CANCELLED


def test_replace_reduces_quantity_and_allocations(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    order = orders.orders[0]
    command = ReplaceOrderCommand(
        command_id="replace", event_time=NOW + timedelta(milliseconds=1), order_id=order.order_id,
        new_quantity=Decimal("3"), new_limit_price=Decimal("101"), reason_code="REDUCE_ORDER",
    )
    result = m05_engine.execute(orders, (stock_events[1],), (command,), stock_bundle, context, policies.execution)
    assert result.final_status_by_order[order.order_id] == OrderStatus.FILLED
    assert sum(fill.quantity for fill in result.fill_events) == Decimal("3")
    assert sum(a.allocated_target_quantity for a in result.fill_events[0].virtual_allocations) == Decimal("3")


def test_replace_cannot_increase_authorized_quantity(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    order = orders.orders[0]
    command = ReplaceOrderCommand(
        command_id="replace", event_time=NOW + timedelta(milliseconds=1), order_id=order.order_id,
        new_quantity=order.quantity + Decimal("1"), reason_code="ILLEGAL_INCREASE",
    )
    with pytest.raises(StateTransitionError):
        m05_engine.execute(orders, (), (command,), stock_bundle, context, policies.execution)


def test_latency_uses_available_at(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    policy = policies.execution.model_copy(update={"latency_milliseconds": 1000})
    result = m05_engine.execute(orders, stock_events, (), stock_bundle, context, policy)
    assert result.fill_events
    assert result.fill_events[0].event_time == NOW + timedelta(seconds=1)


def test_wrong_venue_event_is_ignored(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    quote = stock_market.quotes[0].model_copy(update={"venue": "OTHER", "event_time": NOW + timedelta(seconds=1), "available_at": NOW + timedelta(seconds=1)})
    event = QuoteEvent(event_id="other", event_time=quote.event_time, available_at=quote.available_at, quote=quote)
    result = m05_engine.execute(orders, (event,), (), stock_bundle, context, policies.execution)
    assert result.fill_events == ()
    assert set(result.final_status_by_order.values()) == {OrderStatus.EXPIRED}


def test_halt_cancels_orders(stock_bundle, stock_market, context, venue_capabilities, policies):
    orders = _single_order(stock_bundle, stock_market, context, venue_capabilities, policies)
    command = RuntimeControlCommand(
        command_id="halt", event_time=NOW + timedelta(milliseconds=1), mode=RuntimeControlMode.HALT,
        reason_code="CRITICAL_RUNTIME_STATE",
    )
    result = m05_engine.execute(orders, (), (command,), stock_bundle, context, policies.execution)
    assert set(result.final_status_by_order.values()) == {OrderStatus.CANCELLED}


def test_replace_rejected_when_venue_capability_disallows_it(stock_bundle, stock_market, context, venue_capabilities, policies):
    caps = tuple(item.model_copy(update={"supports_replace": False}) for item in venue_capabilities)
    orders = _single_order(stock_bundle, stock_market, context, caps, policies)
    order = orders.orders[0]
    command = ReplaceOrderCommand(
        command_id="replace-disabled", event_time=NOW + timedelta(milliseconds=1), order_id=order.order_id,
        new_quantity=Decimal("3"), reason_code="REPLACE_REQUEST",
    )
    with pytest.raises(StateTransitionError, match="does not allow"):
        m05_engine.execute(orders, (), (command,), stock_bundle, context, policies.execution)
