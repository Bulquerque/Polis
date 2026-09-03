from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.agents.a4.conftest import NOW, make_bundle, make_s8_input
from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import (
    CandidateAllocation,
    CurrentPosition,
    CurrentVirtualPosition,
    ExecutableTarget,
    ExecutionAuthorization,
)
from quant_pipeline.phase_08_portfolio_control.foundation.enums import (
    AuthorizationStatus,
    OrderType,
    PositionIntent,
    RiskRole,
    RuntimeControlMode,
    TimeInForce,
    Urgency,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import (
    MarketStateSnapshot,
    RuntimeControlCommand,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.runner import run as run_s7
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.accounting_models import (
    BorrowFeeEvent,
    CashAdjustmentEvent,
    CollateralTransferEvent,
    MarginChangeEvent,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.enums import (
    CashAdjustmentType,
    ManagementActionType,
    ManagementSignalType,
    MarkType,
    ValuationStatus,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.errors import (
    ValuationIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.management_models import (
    ManagementSignal,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.prior_state_models import (
    CurrencyAccountState,
    PriorPhysicalPosition,
    PriorPortfolioState,
    PriorVirtualPosition,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.valuation_models import (
    MarkRecord,
    MarkSelectionPolicy,
    MarkSnapshot,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.base_models import FxRate
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.input_models import S8PolicyBundle
from quant_pipeline.phase_08_portfolio_control import run_s8


def _empty_result(stock_instrument, context, venue_capabilities, policies):
    bundle = make_bundle((), (), (stock_instrument,))
    market = MarketStateSnapshot(
        snapshot_id="empty-market", as_of_time=NOW, quotes=(), venue_states={"SIM": "OPEN"},
    )
    return bundle, run_s7(bundle, market, (), (), venue_capabilities, policies, context)


def test_account_events_balance_and_separate_margin_from_expense(
    stock_instrument, context, venue_capabilities, policies, s8_prior_cash,
):
    bundle, result = _empty_result(stock_instrument, context, venue_capabilities, policies)
    t = NOW + timedelta(seconds=1)
    events = (
        CollateralTransferEvent(
            event_id="collateral", event_time=t, available_at=t, currency="USD",
            amount_to_restricted=Decimal("500"), reason_code="TEST",
        ),
        CashAdjustmentEvent(
            event_id="deposit", event_time=t, available_at=t, currency="USD",
            amount=Decimal("100"), adjustment_type=CashAdjustmentType.DEPOSIT,
            reason_code="TEST",
        ),
        CashAdjustmentEvent(
            event_id="dividend", event_time=t, available_at=t, currency="USD",
            amount=Decimal("20"), adjustment_type=CashAdjustmentType.DIVIDEND,
            reason_code="TEST",
        ),
        BorrowFeeEvent(
            event_id="borrow", event_time=t, available_at=t, currency="USD",
            amount=Decimal("5"), reason_code="TEST",
        ),
        MarginChangeEvent(
            event_id="margin", event_time=t, available_at=t, currency="USD",
            new_margin_used=Decimal("1000"), reason_code="TEST",
        ),
    )
    marks = MarkSnapshot(snapshot_id="m", valuation_time=t, marks=(), fx_rates=())
    value = make_s8_input(bundle, result, s8_prior_cash, marks, account_events=events)
    out = run_s8(value)
    account = out.accounting.accounts[0]
    assert account.cash_available == Decimal("9615")
    assert account.collateral_restricted == Decimal("500")
    assert account.margin_used == Decimal("1000")
    assert out.accounting.external_flow_delta == Decimal("100")
    assert sum(x.amount for x in out.accounting.cost_ledger) == Decimal("5")
    assert out.valuation.nav.total_nav == Decimal("10115")
    assert out.valuation.nav.period_pnl == Decimal("15")


def test_collateral_cannot_become_negative(
    stock_instrument, context, venue_capabilities, policies, s8_prior_cash,
):
    bundle, result = _empty_result(stock_instrument, context, venue_capabilities, policies)
    t = NOW + timedelta(seconds=1)
    event = CollateralTransferEvent(
        event_id="bad-collateral", event_time=t, available_at=t, currency="USD",
        amount_to_restricted=Decimal("-1"), reason_code="TEST",
    )
    marks = MarkSnapshot(snapshot_id="m", valuation_time=t, marks=(), fx_rates=())
    value = make_s8_input(bundle, result, s8_prior_cash, marks, account_events=(event,))
    from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.errors import AccountingIntegrityError
    with pytest.raises(AccountingIntegrityError):
        run_s8(value)


def _prior_stock() -> PriorPortfolioState:
    return PriorPortfolioState(
        state_id="prior-stock", as_of_time=NOW,
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


def _holding_bundle(stock_instrument):
    return make_bundle(
        (), (), (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("10")),),
        virtual_positions=(CurrentVirtualPosition(
            candidate_id="c1", instrument_id="AAPL", quantity=Decimal("10"),
        ),),
    )


def test_missing_mark_preserves_incomplete_nav_and_management_hold(
    stock_instrument, context, venue_capabilities, policies,
):
    bundle = _holding_bundle(stock_instrument)
    market = MarketStateSnapshot(snapshot_id="empty", as_of_time=NOW, quotes=(), venue_states={"SIM": "OPEN"})
    result = run_s7(bundle, market, (), (), venue_capabilities, policies, context)
    t = NOW + timedelta(seconds=1)
    value = make_s8_input(
        bundle, result, _prior_stock(),
        MarkSnapshot(snapshot_id="missing", valuation_time=t, marks=(), fx_rates=()),
    )
    out = run_s8(value)
    assert out.valuation.nav.status == ValuationStatus.INCOMPLETE
    assert out.valuation.nav.total_nav is None
    assert out.valuation.nav.known_nav_component == Decimal("9000")
    assert out.valuation.nav.unpriced_instruments == ("AAPL",)
    assert any(a.reason_code == "VALUATION_INCOMPLETE" for a in out.management.actions)


def test_stale_mark_can_be_explicitly_allowed_and_is_degraded(
    stock_instrument, context, venue_capabilities, policies,
):
    bundle = _holding_bundle(stock_instrument)
    market = MarketStateSnapshot(snapshot_id="empty", as_of_time=NOW, quotes=(), venue_states={"SIM": "OPEN"})
    result = run_s7(bundle, market, (), (), venue_capabilities, policies, context)
    t = NOW + timedelta(minutes=10)
    mark = MarkRecord(
        mark_id="stale", instrument_id="AAPL", mark_type=MarkType.MID,
        price=Decimal("101"), event_time=NOW, available_at=NOW,
    )
    policy = S8PolicyBundle(
        policy_version="1.0.0",
        mark_selection=MarkSelectionPolicy(stale_after_seconds=60, allow_stale=True),
    )
    value = make_s8_input(
        bundle, result, _prior_stock(),
        MarkSnapshot(snapshot_id="stale", valuation_time=t, marks=(mark,), fx_rates=()),
        policies=policy,
    )
    out = run_s8(value)
    assert out.valuation.nav.status == ValuationStatus.DEGRADED
    assert out.valuation.positions[0].mark_type == MarkType.STALE
    assert out.valuation.nav.total_nav == Decimal("10010")


def test_fx_conversion_and_duplicate_inconsistent_rate_rejected(
    stock_instrument, context, venue_capabilities, policies,
):
    bundle, result = _empty_result(stock_instrument, context, venue_capabilities, policies)
    prior = PriorPortfolioState(
        state_id="eur", as_of_time=NOW,
        accounts=(CurrencyAccountState(currency="EUR", cash_available=Decimal("100")),),
        opening_nav_functional=Decimal("120"), functional_currency="USD",
    )
    t = NOW + timedelta(seconds=1)
    fx = FxRate(currency="EUR", functional_currency="USD", rate=Decimal("1.2"), available_at=t)
    marks = MarkSnapshot(snapshot_id="fx", valuation_time=t, marks=(), fx_rates=(fx,))
    out = run_s8(make_s8_input(bundle, result, prior, marks))
    assert out.valuation.nav.total_nav == Decimal("120.0")
    bad_fx = FxRate(currency="EUR", functional_currency="USD", rate=Decimal("1.3"), available_at=t)
    bad_marks = marks.model_copy(update={"fx_rates": (fx, bad_fx)})
    with pytest.raises(ValuationIntegrityError):
        run_s8(make_s8_input(bundle, result, prior, bad_marks))


def test_runtime_command_and_signal_create_bounded_actions(
    stock_instrument, context, venue_capabilities, policies, s8_prior_cash,
):
    bundle, result = _empty_result(stock_instrument, context, venue_capabilities, policies)
    t = NOW + timedelta(seconds=1)
    command = RuntimeControlCommand(
        command_id="halt", event_time=t, mode=RuntimeControlMode.HALT, reason_code="TEST",
    )
    signal = ManagementSignal(
        signal_id="sig", event_time=t,
        signal_type=ManagementSignalType.RISK_REDUCTION_REQUIRED,
        reason_code="RISK_CHANGED", affected_instrument_ids=("AAPL",),
    )
    value = make_s8_input(
        bundle, result, s8_prior_cash,
        MarkSnapshot(snapshot_id="m", valuation_time=t, marks=(), fx_rates=()),
        runtime_commands=(command,), management_signals=(signal,),
    )
    out = run_s8(value)
    action_types = {a.action_type for a in out.management.actions}
    assert ManagementActionType.HALT in action_types
    assert ManagementActionType.REQUEST_REOPTIMIZATION in action_types
    assert out.management.reoptimization_requests[0].affected_instrument_ids == ("AAPL",)
