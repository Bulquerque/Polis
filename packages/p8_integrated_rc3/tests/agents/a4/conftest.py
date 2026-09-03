from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.contracts.common import ArtifactReference, LineageEdge
from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import (
    CandidateAllocation,
    CurrentPosition,
    CurrentVirtualPosition,
    ExecutableTarget,
    ExecutionAuthorization,
    InstrumentSpec,
    P8ExecutionAuthorizationBundle,
    execution_authorization_payload_hash,
    seal_execution_authorization_bundle,
)
from quant_pipeline.phase_08_portfolio_control.foundation.context import ModuleExecutionContext
from quant_pipeline.phase_08_portfolio_control.foundation.enums import (
    AuthorizationStatus,
    OrderType,
    PositionIntent,
    RiskRole,
    SecurityType,
    TimeInForce,
    Urgency,
    VenueState,
)
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import (
    MarketStateSnapshot,
    Quote,
    QuoteEvent,
    VenueCapabilities,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.policies import (
    CostPolicy,
    ExecutionModelPolicy,
    IntentPolicy,
    RoutingPolicy,
    S7PolicyBundle,
    StructurePolicy,
)

NOW = datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)


def ref(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        content_sha256="a" * 64,
        contract_version="1.0.0",
        schema_version="1.0.0",
    )


@pytest.fixture
def context() -> ModuleExecutionContext:
    return ModuleExecutionContext(
        run_id="run-1", cycle_id="cycle-1", decision_time=NOW,
        market_cutoff_at=NOW, trace_id="trace-1", policy_version="1.0.0",
    )


@pytest.fixture
def stock_instrument() -> InstrumentSpec:
    return InstrumentSpec(
        instrument_id="AAPL", symbol="AAPL", security_type=SecurityType.EQUITY,
        currency="USD", lot_size=Decimal("1"), quantity_increment=Decimal("1"),
        contract_multiplier=Decimal("1"), valid_from=NOW-timedelta(days=100),
    )


@pytest.fixture
def option_instruments() -> tuple[InstrumentSpec, InstrumentSpec]:
    exp = NOW + timedelta(days=30)
    return (
        InstrumentSpec(
            instrument_id="AAPL_C100", symbol="AAPL_C100", security_type=SecurityType.OPTION,
            currency="USD", lot_size=Decimal("1"), quantity_increment=Decimal("1"),
            contract_multiplier=Decimal("100"), valid_from=NOW-timedelta(days=10),
            underlying_id="AAPL", expiration=exp,
        ),
        InstrumentSpec(
            instrument_id="AAPL_C110", symbol="AAPL_C110", security_type=SecurityType.OPTION,
            currency="USD", lot_size=Decimal("1"), quantity_increment=Decimal("1"),
            contract_multiplier=Decimal("100"), valid_from=NOW-timedelta(days=10),
            underlying_id="AAPL", expiration=exp,
        ),
    )


def make_bundle(targets, auths, instruments, positions=(), virtual_positions=(), open_orders=()) -> P8ExecutionAuthorizationBundle:
    payload = dict(
        bundle_id="bundle-1", producer_release="agent3-1.0", run_id="run-1", cycle_id="cycle-1",
        decision_time=NOW, valid_until=NOW+timedelta(hours=1), targets=tuple(targets),
        authorizations=tuple(auths), instruments=tuple(instruments), current_positions=tuple(positions),
        current_virtual_positions=tuple(virtual_positions), open_orders=tuple(open_orders),
        dual_book_map_ref=ref("dual"), risk_gate_ref=ref("risk"), hedge_plan_ref=ref("hedge"),
        lifecycle_plan_ref=ref("life"), lineage=(LineageEdge(
            parent_artifact_id="p8-s6", parent_content_sha256="b"*64, relationship_type="CONSUMES"
        ),), content_sha256="0"*64,
    )
    provisional = P8ExecutionAuthorizationBundle(**payload)
    return seal_execution_authorization_bundle(provisional)


@pytest.fixture
def stock_bundle(stock_instrument) -> P8ExecutionAuthorizationBundle:
    target = ExecutableTarget(
        target_id="t1", authorization_id="a1", execution_group_id="g1", instrument_id="AAPL",
        target_quantity=Decimal("10"), urgency=Urgency.NORMAL, risk_role=RiskRole.NEUTRAL,
        position_intent=PositionIntent.BUY_TO_OPEN,
        virtual_allocations=(CandidateAllocation(candidate_id="c1", allocated_target_quantity=Decimal("10")),),
    )
    auth = ExecutionAuthorization(
        authorization_id="a1", target_id="t1", status=AuthorizationStatus.AUTHORIZED,
        valid_until=NOW+timedelta(hours=1), allowed_order_types=(OrderType.LIMIT, OrderType.MARKET),
        allowed_time_in_force=(TimeInForce.DAY, TimeInForce.IOC, TimeInForce.FOK),
        allow_legging=False, allow_market_order=True, max_participation_rate=Decimal("1"),
        price_protection_bps=Decimal("200"), preferred_venues=("SIM",),
    )
    return make_bundle((target,), (auth,), (stock_instrument,))


@pytest.fixture
def stock_market() -> MarketStateSnapshot:
    quote = Quote(
        instrument_id="AAPL", event_time=NOW, available_at=NOW,
        bid_price=Decimal("99"), ask_price=Decimal("101"),
        bid_size=Decimal("100"), ask_size=Decimal("6"), venue="SIM",
    )
    return MarketStateSnapshot(snapshot_id="m1", as_of_time=NOW, quotes=(quote,), venue_states={"SIM": VenueState.OPEN})


@pytest.fixture
def stock_events(stock_market):
    q1 = stock_market.quotes[0]
    q2 = q1.model_copy(update={"event_time": NOW+timedelta(seconds=1), "available_at": NOW+timedelta(seconds=1), "ask_size": Decimal("10")})
    return (
        QuoteEvent(event_id="qe1", event_time=NOW, available_at=NOW, quote=q1),
        QuoteEvent(event_id="qe2", event_time=NOW+timedelta(seconds=1), available_at=NOW+timedelta(seconds=1), quote=q2),
    )


@pytest.fixture
def venue_capabilities():
    return (VenueCapabilities(
        venue="SIM", supports_combo=True,
        supported_security_types=(SecurityType.EQUITY, SecurityType.OPTION),
        supported_order_types=(OrderType.MARKET, OrderType.LIMIT),
        supported_tifs=(TimeInForce.DAY, TimeInForce.IOC, TimeInForce.FOK, TimeInForce.GTC),
    ),)


@pytest.fixture
def policies():
    return S7PolicyBundle(
        intent=IntentPolicy(), structure=StructurePolicy(),
        routing=RoutingPolicy(default_venue="SIM", max_slice_quantity=Decimal("20"), order_lifetime_seconds=60),
        cost=CostPolicy(
            fee_per_unit=Decimal("0.01"), minimum_fee=Decimal("0"), slippage_bps=Decimal("1"),
            impact_coefficient=Decimal("0.0001"), annualized_volatility=Decimal("0.2"),
            delay_bps=Decimal("0.5"), opportunity_bps=Decimal("0.5"),
            legging_bps=Decimal("1"), borrow_bps=Decimal("0"),
        ),
        execution=ExecutionModelPolicy(aggressive_slippage_bps=Decimal("0"), fee_per_unit=Decimal("0.01")),
    )

# ---- P8.S8 fixtures ----
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.runner import run as run_s7
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.input_models import (
    S7ToS8Handoff, S8InputBundle, S8PolicyBundle,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.prior_state_models import (
    CurrencyAccountState, PriorPhysicalPosition, PriorPortfolioState, PriorVirtualPosition,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.sealing import (
    seal_s7_handoff, seal_s8_input,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.valuation_models import (
    MarkRecord, MarkSnapshot,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.enums import MarkType


@pytest.fixture
def s7_linear_result(stock_bundle, stock_market, stock_events, context, venue_capabilities, policies):
    return run_s7(stock_bundle, stock_market, stock_events, (), venue_capabilities, policies, context)


def make_handoff(bundle, result, handoff_id="handoff-1"):
    provisional = S7ToS8Handoff(
        handoff_id=handoff_id, producer_release="s7-1.0.0", run_id=bundle.run_id,
        cycle_id=bundle.cycle_id, decision_time=bundle.decision_time,
        authorization_bundle=bundle, s7_result=result, content_sha256="0"*64,
    )
    return seal_s7_handoff(provisional)


def make_s8_input(bundle, result, prior, marks, **updates):
    handoff = make_handoff(bundle, result)
    payload = dict(
        bundle_id="s8-input-1", run_id=bundle.run_id, cycle_id=bundle.cycle_id,
        decision_time=bundle.decision_time, valuation_time=marks.valuation_time,
        s7_handoff=handoff, prior_state=prior, marks=marks,
        policies=S8PolicyBundle(policy_version="1.0.0"), content_sha256="0"*64,
    )
    payload.update(updates)
    return seal_s8_input(S8InputBundle(**payload))


@pytest.fixture
def s8_prior_cash():
    return PriorPortfolioState(
        state_id="prior-1", as_of_time=NOW,
        accounts=(CurrencyAccountState(currency="USD", cash_available=Decimal("10000")),),
        opening_nav_functional=Decimal("10000"), functional_currency="USD",
    )


@pytest.fixture
def s8_linear_marks():
    when = NOW + timedelta(seconds=2)
    return MarkSnapshot(
        snapshot_id="marks-1", valuation_time=when,
        marks=(MarkRecord(
            mark_id="mark-aapl", instrument_id="AAPL", mark_type=MarkType.MID,
            price=Decimal("102"), event_time=when, available_at=when,
        ),), fx_rates=(),
    )


@pytest.fixture
def s8_linear_input(stock_bundle, s7_linear_result, s8_prior_cash, s8_linear_marks):
    return make_s8_input(stock_bundle, s7_linear_result, s8_prior_cash, s8_linear_marks)
