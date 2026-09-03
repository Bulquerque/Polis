from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.agents.a4.conftest import NOW, make_bundle, make_s8_input
from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import (
    CurrentPosition,
    CurrentVirtualPosition,
    InstrumentSpec,
)
from quant_pipeline.phase_08_portfolio_control.foundation.enums import SecurityType
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import MarketStateSnapshot
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.runner import run as run_s7
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine import (
    m01_timeline,
    m02_execution_state,
    m03_positions,
    m04_accounting,
    m05_valuation,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.enums import (
    ExerciseStyle,
    MarkType,
    OptionType,
    SettlementType,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.errors import (
    LifecycleIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.lifecycle_models import (
    LifecycleCandidateAllocation,
    OptionAssignmentEvent,
    OptionCashSettlementEvent,
    OptionContractSpec,
    OptionExerciseEvent,
    OptionExpirationEvent,
    SplitEvent,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.prior_state_models import (
    CurrencyAccountState,
    PriorPhysicalPosition,
    PriorPortfolioState,
    PriorVirtualPosition,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.valuation_models import (
    MarkRecord,
    MarkSnapshot,
)

EXPIRY = NOW + timedelta(days=30)
EVENT_TIME = EXPIRY + timedelta(seconds=1)


def _option_instrument(multiplier: Decimal = Decimal("100")) -> InstrumentSpec:
    return InstrumentSpec(
        instrument_id="AAPL_C100",
        symbol="AAPL_C100",
        security_type=SecurityType.OPTION,
        currency="USD",
        lot_size=Decimal("1"),
        quantity_increment=Decimal("1"),
        contract_multiplier=multiplier,
        valid_from=NOW - timedelta(days=10),
        valid_until=EXPIRY,
        underlying_id="AAPL",
        expiration=EXPIRY,
    )


def _underlying() -> InstrumentSpec:
    return InstrumentSpec(
        instrument_id="AAPL",
        symbol="AAPL",
        security_type=SecurityType.EQUITY,
        currency="USD",
        lot_size=Decimal("1"),
        quantity_increment=Decimal("1"),
        contract_multiplier=Decimal("1"),
        valid_from=NOW - timedelta(days=100),
    )


def _option_contract(settlement: SettlementType) -> OptionContractSpec:
    return OptionContractSpec(
        instrument_id="AAPL_C100",
        underlying_id="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("100"),
        expiration=EXPIRY,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=settlement,
        contract_multiplier=Decimal("100"),
        currency="USD",
    )


def _prior(quantity: Decimal, basis: Decimal, cash: Decimal) -> PriorPortfolioState:
    average = abs(basis) / (abs(quantity) * Decimal("100"))
    return PriorPortfolioState(
        state_id="prior-option",
        as_of_time=NOW,
        physical_positions=(PriorPhysicalPosition(
            instrument_id="AAPL_C100", quantity=quantity,
            signed_cost_basis=basis, average_entry_price=average, opened_at=NOW,
        ),),
        virtual_positions=(PriorVirtualPosition(
            candidate_id="c-opt", instrument_id="AAPL_C100", quantity=quantity,
            signed_cost_basis=basis, average_entry_price=average, opened_at=NOW,
        ),),
        accounts=(CurrencyAccountState(currency="USD", cash_available=cash),),
        opening_nav_functional=Decimal("10000"),
        functional_currency="USD",
    )


def _input(
    quantity: Decimal,
    basis: Decimal,
    cash: Decimal,
    lifecycle_event,
    settlement: SettlementType,
    context,
    venue_capabilities,
    policies,
    marks: tuple[MarkRecord, ...] = (),
):
    option = _option_instrument()
    bundle = make_bundle(
        (), (), (option,),
        positions=(CurrentPosition(instrument_id=option.instrument_id, quantity=quantity),),
        virtual_positions=(CurrentVirtualPosition(
            candidate_id="c-opt", instrument_id=option.instrument_id, quantity=quantity,
        ),),
    )
    market = MarketStateSnapshot(
        snapshot_id="empty", as_of_time=NOW, quotes=(), venue_states={"SIM": "OPEN"},
    )
    s7_result = run_s7(bundle, market, (), (), venue_capabilities, policies, context)
    mark_snapshot = MarkSnapshot(
        snapshot_id="lifecycle-marks", valuation_time=EVENT_TIME,
        marks=marks, fx_rates=(),
    )
    return make_s8_input(
        bundle, s7_result, _prior(quantity, basis, cash), mark_snapshot,
        option_contracts=(_option_contract(settlement),),
        supplemental_instruments=(_underlying(),),
        lifecycle_events=(lifecycle_event,),
    )


def _run(value):
    queue = m01_timeline.execute(value)
    execution = m02_execution_state.execute(value, queue)
    positions = m03_positions.execute(value, queue, execution)
    accounting = m04_accounting.execute(value, queue, positions)
    valuation = m05_valuation.execute(value, positions, accounting)
    return positions, accounting, valuation


def _allocation(quantity: Decimal) -> tuple[LifecycleCandidateAllocation, ...]:
    return (LifecycleCandidateAllocation(
        candidate_id="c-opt", instrument_id="AAPL_C100",
        signed_contract_quantity=quantity, event_time=EVENT_TIME,
    ),)


def test_long_call_exercise_creates_underlying_and_preserves_nav(
    context, venue_capabilities, policies,
):
    event = OptionExerciseEvent(
        event_id="exercise-1", event_time=EVENT_TIME, available_at=EVENT_TIME,
        instrument_id="AAPL_C100", contract_quantity=Decimal("1"),
        candidate_allocations=_allocation(Decimal("1")),
    )
    marks = (MarkRecord(
        mark_id="m-aapl", instrument_id="AAPL", mark_type=MarkType.MID,
        price=Decimal("102"), event_time=EVENT_TIME, available_at=EVENT_TIME,
    ),)
    value = _input(Decimal("1"), Decimal("200"), Decimal("9800"), event,
                   SettlementType.PHYSICAL, context, venue_capabilities, policies, marks)
    positions, accounting, valuation = _run(value)
    assert [(p.instrument_id, p.quantity) for p in positions.physical_positions] == [("AAPL", Decimal("100"))]
    assert accounting.accounts[0].cash_available == Decimal("-200")
    assert valuation.nav.total_nav == Decimal("10000")
    assert valuation.nav.period_pnl == Decimal("0")


def test_short_call_assignment_creates_short_underlying(
    context, venue_capabilities, policies,
):
    event = OptionAssignmentEvent(
        event_id="assign-1", event_time=EVENT_TIME, available_at=EVENT_TIME,
        instrument_id="AAPL_C100", contract_quantity=Decimal("1"),
        candidate_allocations=_allocation(Decimal("-1")),
    )
    marks = (MarkRecord(
        mark_id="m-aapl", instrument_id="AAPL", mark_type=MarkType.MID,
        price=Decimal("102"), event_time=EVENT_TIME, available_at=EVENT_TIME,
    ),)
    value = _input(Decimal("-1"), Decimal("-200"), Decimal("10200"), event,
                   SettlementType.PHYSICAL, context, venue_capabilities, policies, marks)
    positions, accounting, valuation = _run(value)
    assert positions.physical_positions[0].instrument_id == "AAPL"
    assert positions.physical_positions[0].quantity == Decimal("-100")
    assert accounting.accounts[0].cash_available == Decimal("20200")
    assert valuation.nav.total_nav == Decimal("10000")


def test_cash_settlement_realizes_option_value(context, venue_capabilities, policies):
    event = OptionCashSettlementEvent(
        event_id="cash-settle-1", event_time=EVENT_TIME, available_at=EVENT_TIME,
        instrument_id="AAPL_C100", contract_quantity=Decimal("1"),
        candidate_allocations=_allocation(Decimal("1")),
        cash_amount=Decimal("500"), currency="USD",
    )
    value = _input(Decimal("1"), Decimal("200"), Decimal("9800"), event,
                   SettlementType.CASH, context, venue_capabilities, policies)
    positions, accounting, valuation = _run(value)
    assert not positions.physical_positions
    assert accounting.accounts[0].cash_available == Decimal("10300")
    assert valuation.nav.total_nav == Decimal("10300")
    assert valuation.nav.period_pnl == Decimal("300")


def test_expiration_worthless_realizes_premium_loss(context, venue_capabilities, policies):
    event = OptionExpirationEvent(
        event_id="expire-1", event_time=EVENT_TIME, available_at=EVENT_TIME,
        instrument_id="AAPL_C100", contract_quantity=Decimal("1"),
        candidate_allocations=_allocation(Decimal("1")),
    )
    value = _input(Decimal("1"), Decimal("200"), Decimal("9800"), event,
                   SettlementType.PHYSICAL, context, venue_capabilities, policies)
    positions, accounting, valuation = _run(value)
    assert not positions.physical_positions
    assert accounting.accounts[0].cash_available == Decimal("9800")
    assert valuation.nav.total_nav == Decimal("9800")
    assert valuation.nav.period_pnl == Decimal("-200")


def test_expiration_before_contract_expiry_is_rejected(context, venue_capabilities, policies):
    early = NOW + timedelta(days=1)
    event = OptionExpirationEvent(
        event_id="expire-early", event_time=early, available_at=early,
        instrument_id="AAPL_C100", contract_quantity=Decimal("1"),
        candidate_allocations=(LifecycleCandidateAllocation(
            candidate_id="c-opt", instrument_id="AAPL_C100",
            signed_contract_quantity=Decimal("1"), event_time=early,
        ),),
    )
    marks = MarkSnapshot(snapshot_id="early", valuation_time=early, marks=(), fx_rates=())
    option = _option_instrument()
    bundle = make_bundle(
        (), (), (option,),
        positions=(CurrentPosition(instrument_id=option.instrument_id, quantity=Decimal("1")),),
        virtual_positions=(CurrentVirtualPosition(
            candidate_id="c-opt", instrument_id=option.instrument_id, quantity=Decimal("1"),
        ),),
    )
    market = MarketStateSnapshot(snapshot_id="empty", as_of_time=NOW, quotes=(), venue_states={"SIM": "OPEN"})
    s7_result = run_s7(bundle, market, (), (), venue_capabilities, policies, context)
    value = make_s8_input(
        bundle, s7_result, _prior(Decimal("1"), Decimal("200"), Decimal("9800")), marks,
        option_contracts=(_option_contract(SettlementType.PHYSICAL),),
        supplemental_instruments=(_underlying(),), lifecycle_events=(event,),
    )
    queue = m01_timeline.execute(value)
    execution = m02_execution_state.execute(value, queue)
    with pytest.raises(LifecycleIntegrityError):
        m03_positions.execute(value, queue, execution)


def test_equity_split_preserves_basis_and_doubles_quantity(
    stock_instrument, context, venue_capabilities, policies,
):
    event_time = NOW + timedelta(seconds=1)
    bundle = make_bundle(
        (), (), (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("10")),),
        virtual_positions=(CurrentVirtualPosition(
            candidate_id="c1", instrument_id="AAPL", quantity=Decimal("10"),
        ),),
    )
    market = MarketStateSnapshot(snapshot_id="empty", as_of_time=NOW, quotes=(), venue_states={"SIM": "OPEN"})
    s7_result = run_s7(bundle, market, (), (), venue_capabilities, policies, context)
    prior = PriorPortfolioState(
        state_id="prior-split", as_of_time=NOW,
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
    split = SplitEvent(
        event_id="split-1", event_time=event_time, available_at=event_time,
        instrument_id="AAPL", ratio_numerator=Decimal("2"), ratio_denominator=Decimal("1"),
    )
    marks = MarkSnapshot(
        snapshot_id="split-marks", valuation_time=event_time,
        marks=(MarkRecord(
            mark_id="m-split", instrument_id="AAPL", mark_type=MarkType.MID,
            price=Decimal("51"), event_time=event_time, available_at=event_time,
        ),), fx_rates=(),
    )
    value = make_s8_input(bundle, s7_result, prior, marks, lifecycle_events=(split,))
    positions, accounting, valuation = _run(value)
    assert positions.physical_positions[0].quantity == Decimal("20")
    assert positions.physical_positions[0].signed_cost_basis == Decimal("1000")
    assert positions.physical_positions[0].average_entry_price == Decimal("50")
    assert accounting.accounts[0].cash_available == Decimal("9000")
    assert valuation.nav.total_nav == Decimal("10020")
