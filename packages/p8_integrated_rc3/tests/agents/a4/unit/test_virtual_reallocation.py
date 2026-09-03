from datetime import timedelta
from decimal import Decimal

from tests.agents.a4.conftest import NOW, make_bundle, make_s8_input
from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import (
    CandidateAllocation, CurrentPosition, CurrentVirtualPosition, ExecutableTarget,
    ExecutionAuthorization,
)
from quant_pipeline.phase_08_portfolio_control.foundation.enums import (
    AuthorizationStatus, OrderType, PositionIntent, RiskRole, TimeInForce, Urgency,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import MarketStateSnapshot
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.runner import run as run_s7
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.prior_state_models import (
    CurrencyAccountState, PriorPhysicalPosition, PriorPortfolioState, PriorVirtualPosition,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.valuation_models import MarkRecord, MarkSnapshot
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.enums import MarkType
from quant_pipeline.phase_08_portfolio_control import run_s8


def test_virtual_reallocation_moves_cost_basis_without_physical_order(
    stock_instrument, context, venue_capabilities, policies,
):
    target = ExecutableTarget(
        target_id="t-realloc", authorization_id="a-realloc", execution_group_id="g",
        instrument_id="AAPL", target_quantity=Decimal("10"), urgency=Urgency.NORMAL,
        risk_role=RiskRole.NEUTRAL, position_intent=PositionIntent.BUY_TO_OPEN,
        virtual_allocations=(CandidateAllocation(
            candidate_id="c2", allocated_target_quantity=Decimal("10"),
        ),),
    )
    auth = ExecutionAuthorization(
        authorization_id="a-realloc", target_id="t-realloc",
        status=AuthorizationStatus.AUTHORIZED, valid_until=NOW+timedelta(hours=1),
        allowed_order_types=(OrderType.LIMIT,), allowed_time_in_force=(TimeInForce.DAY,),
        allow_legging=False, allow_market_order=False,
        max_participation_rate=Decimal("1"), price_protection_bps=Decimal("100"),
        preferred_venues=("SIM",),
    )
    bundle = make_bundle(
        (target,), (auth,), (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("10")),),
        virtual_positions=(CurrentVirtualPosition(
            candidate_id="c1", instrument_id="AAPL", quantity=Decimal("10"),
        ),),
    )
    market = MarketStateSnapshot(snapshot_id="empty", as_of_time=NOW, quotes=(), venue_states={"SIM":"OPEN"})
    s7 = run_s7(bundle, market, (), (), venue_capabilities, policies, context)
    assert not s7.planned_orders.orders
    assert len(s7.receipt.virtual_reallocations) == 2
    prior = PriorPortfolioState(
        state_id="prior", as_of_time=NOW,
        physical_positions=(PriorPhysicalPosition(
            instrument_id="AAPL", quantity=Decimal("10"), signed_cost_basis=Decimal("1000"),
            average_entry_price=Decimal("100"), opened_at=NOW,
        ),),
        virtual_positions=(PriorVirtualPosition(
            candidate_id="c1", instrument_id="AAPL", quantity=Decimal("10"),
            signed_cost_basis=Decimal("1000"), average_entry_price=Decimal("100"), opened_at=NOW,
        ),),
        accounts=(CurrencyAccountState(currency="USD", cash_available=Decimal("9000")),),
        opening_nav_functional=Decimal("10000"), functional_currency="USD",
    )
    t=NOW+timedelta(seconds=1)
    marks=MarkSnapshot(snapshot_id="m",valuation_time=t,marks=(MarkRecord(
        mark_id="m1",instrument_id="AAPL",mark_type=MarkType.MID,price=Decimal("100"),
        event_time=t,available_at=t),),fx_rates=())
    out=run_s8(make_s8_input(bundle,s7,prior,marks))
    assert out.positions.physical_positions[0].quantity == Decimal("10")
    assert [(p.candidate_id,p.quantity,p.signed_cost_basis) for p in out.positions.virtual_positions] == [
        ("c2",Decimal("10"),Decimal("1000"))
    ]
    assert not out.execution_state.orders
    assert out.valuation.nav.total_nav == Decimal("10000")
