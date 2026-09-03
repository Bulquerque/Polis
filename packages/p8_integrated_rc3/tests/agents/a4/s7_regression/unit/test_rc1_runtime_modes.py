from __future__ import annotations

from datetime import timedelta

import pytest

from tests.agents.a4.conftest import NOW
from quant_pipeline.phase_08_portfolio_control.foundation.enums import (
    OrderStatus,
    PositionIntent,
    RiskRole,
    RuntimeControlMode,
)
from quant_pipeline.phase_08_portfolio_control.foundation.errors import StateTransitionError
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import (
    m01_intents,
    m02_structure,
    m03_routing,
    m05_engine,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import RuntimeControlCommand


def _orders(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents = m01_intents.execute(stock_bundle, context, policies.intent)
    structures = m02_structure.execute(intents, stock_bundle, venue_capabilities, policies.structure)
    return m03_routing.execute(
        intents, structures, stock_bundle, stock_market, venue_capabilities, context, policies.routing
    )


def _order_with(orders, role: RiskRole, position_intent: PositionIntent):
    order = orders.orders[0]
    legs = tuple(leg.model_copy(update={"position_intent": position_intent}) for leg in order.legs)
    order = order.model_copy(update={"risk_role": role, "legs": legs})
    return orders.model_copy(update={"orders": (order,)})


@pytest.mark.parametrize(
    ("mode", "role", "position_intent", "allowed"),
    [
        (RuntimeControlMode.HOLD_NO_NEW_RISK, RiskRole.NEUTRAL, PositionIntent.BUY_TO_OPEN, False),
        (RuntimeControlMode.HOLD_NO_NEW_RISK, RiskRole.PROTECTIVE, PositionIntent.BUY_TO_OPEN, True),
        (RuntimeControlMode.CLOSE_ONLY, RiskRole.RISK_REDUCING, PositionIntent.SELL_TO_CLOSE, True),
        (RuntimeControlMode.CLOSE_ONLY, RiskRole.RISK_REDUCING, PositionIntent.BUY_TO_OPEN, False),
        (RuntimeControlMode.RISK_REDUCTION_ONLY, RiskRole.RISK_REDUCING, PositionIntent.SELL_TO_CLOSE, True),
        (RuntimeControlMode.RISK_REDUCTION_ONLY, RiskRole.PROTECTIVE, PositionIntent.BUY_TO_OPEN, False),
        (RuntimeControlMode.HEDGE_ONLY, RiskRole.PROTECTIVE, PositionIntent.BUY_TO_OPEN, True),
        (RuntimeControlMode.HEDGE_ONLY, RiskRole.RISK_REDUCING, PositionIntent.SELL_TO_CLOSE, False),
        (RuntimeControlMode.CONTROLLED_FLATTEN, RiskRole.RISK_REDUCING, PositionIntent.SELL_TO_CLOSE, True),
        (RuntimeControlMode.CONTROLLED_FLATTEN, RiskRole.RISK_REDUCING, PositionIntent.BUY_TO_OPEN, False),
    ],
)
def test_runtime_mode_is_enforced_before_submission(
    stock_bundle,
    stock_market,
    stock_events,
    context,
    venue_capabilities,
    policies,
    mode,
    role,
    position_intent,
    allowed,
):
    orders = _order_with(
        _orders(stock_bundle, stock_market, context, venue_capabilities, policies),
        role,
        position_intent,
    )
    command = RuntimeControlCommand(
        command_id=f"cmd-{mode.value}-{role.value}-{position_intent.value}",
        event_time=NOW,
        mode=mode,
        reason_code="RC1_RUNTIME_POLICY",
        command_sequence=1,
        feasibility_proven=True,
    )
    result = m05_engine.execute(
        orders,
        stock_events,
        (command,),
        stock_bundle,
        context,
        policies.execution,
    )
    status = next(iter(result.final_status_by_order.values()))
    assert (status is OrderStatus.FILLED) is allowed
    if not allowed:
        assert status is OrderStatus.CANCELLED
        assert result.fill_events == ()


def test_expired_runtime_command_fails_closed(
    stock_bundle, stock_market, context, venue_capabilities, policies
):
    orders = _orders(stock_bundle, stock_market, context, venue_capabilities, policies)
    command = RuntimeControlCommand(
        command_id="expired",
        event_time=NOW,
        mode=RuntimeControlMode.HALT,
        reason_code="EXPIRED",
        valid_until=NOW - timedelta(microseconds=1),
        command_sequence=1,
    )
    with pytest.raises(StateTransitionError, match="expired runtime command"):
        m05_engine.execute(orders, (), (command,), stock_bundle, context, policies.execution)


def test_runtime_command_without_feasibility_proof_fails_closed(
    stock_bundle, stock_market, context, venue_capabilities, policies
):
    orders = _orders(stock_bundle, stock_market, context, venue_capabilities, policies)
    command = RuntimeControlCommand(
        command_id="unproven",
        event_time=NOW,
        mode=RuntimeControlMode.CONTROLLED_FLATTEN,
        reason_code="UNPROVEN",
        command_sequence=1,
        feasibility_proven=False,
    )
    with pytest.raises(StateTransitionError, match="lacks feasibility proof"):
        m05_engine.execute(orders, (), (command,), stock_bundle, context, policies.execution)
