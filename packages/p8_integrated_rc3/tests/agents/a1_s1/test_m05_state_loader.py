from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_contracts.enums import RuntimeMode, StateQualityStatus
from quant_pipeline.phase_08_contracts.state import AccountSnapshot, CashBalance, PositionRecord
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters import (
    StaticAccountSnapshotAdapter,
    StaticPortfolioStateReader,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import (
    CapabilityError,
    HashMismatchError,
    TemporalIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m05_current_portfolio_and_account_state_loader import (
    run_module,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.policies import StateReconciliationPolicy

from tests.agents.a1_s1.factories import P8_DECISION, context, finalize_hash, full_fixture, make_account_snapshot


def test_backtest_without_external_account_is_usable() -> None:
    fixture = full_fixture(ranked=False, mode=RuntimeMode.BACKTEST, include_external_account=False)
    result = run_module(
        portfolio_reader=fixture.ports.portfolio_state_reader,
        account_port=fixture.ports.account_snapshot_port,
        context=fixture.request.context,
        policy=StateReconciliationPolicy(),
    )
    assert result.current_state.quality_report.status is StateQualityStatus.USABLE_BACKTEST


def test_live_requires_external_account_snapshot() -> None:
    fixture = full_fixture(ranked=False, mode=RuntimeMode.LIVE, include_external_account=False)
    with pytest.raises(CapabilityError):
        run_module(
            portfolio_reader=fixture.ports.portfolio_state_reader,
            account_port=fixture.ports.account_snapshot_port,
            context=fixture.request.context,
            policy=StateReconciliationPolicy(),
        )


def test_matching_external_account_is_usable() -> None:
    fixture = full_fixture(ranked=False, mode=RuntimeMode.LIVE, include_external_account=True)
    result = run_module(
        portfolio_reader=fixture.ports.portfolio_state_reader,
        account_port=fixture.ports.account_snapshot_port,
        context=fixture.request.context,
        policy=StateReconciliationPolicy(),
    )
    assert result.current_state.quality_report.status is StateQualityStatus.USABLE
    assert not result.current_state.quality_report.discrepancies


def test_position_discrepancy_blocks_state() -> None:
    fixture = full_fixture(ranked=False, mode=RuntimeMode.LIVE, include_external_account=True)
    account = fixture.account_snapshot
    assert account is not None
    altered = finalize_hash(
        account.model_copy(
            update={
                "positions": (
                    PositionRecord(
                        instrument_id="OPT-ABC-100-C",
                        quantity=Decimal("3"),
                        contract_multiplier=Decimal("100"),
                        currency="USD",
                    ),
                ),
                "content_sha256": "0" * 64,
            }
        )
    )
    result = run_module(
        portfolio_reader=fixture.ports.portfolio_state_reader,
        account_port=StaticAccountSnapshotAdapter(altered),
        context=fixture.request.context,
        policy=StateReconciliationPolicy(material_discrepancy_limit=0),
    )
    assert result.current_state.quality_report.status is StateQualityStatus.BLOCKED
    assert result.current_state.quality_report.discrepancies[0].category == "POSITION_QUANTITY"


def test_cash_tolerance_avoids_false_discrepancy() -> None:
    fixture = full_fixture(ranked=False, mode=RuntimeMode.LIVE, include_external_account=True)
    account = fixture.account_snapshot
    assert account is not None
    altered = finalize_hash(
        account.model_copy(
            update={
                "cash": (CashBalance(currency="USD", amount=Decimal("100000.005")),),
                "content_sha256": "0" * 64,
            }
        )
    )
    result = run_module(
        portfolio_reader=fixture.ports.portfolio_state_reader,
        account_port=StaticAccountSnapshotAdapter(altered),
        context=fixture.request.context,
        policy=StateReconciliationPolicy(cash_tolerance=Decimal("0.01")),
    )
    assert result.current_state.quality_report.status is StateQualityStatus.USABLE


def test_future_portfolio_state_is_rejected() -> None:
    fixture = full_fixture(ranked=False)
    future = finalize_hash(
        fixture.portfolio_state.model_copy(
            update={"as_of_time": P8_DECISION.replace(microsecond=1), "content_sha256": "0" * 64}
        )
    )
    with pytest.raises(TemporalIntegrityError):
        run_module(
            portfolio_reader=StaticPortfolioStateReader(future),
            account_port=StaticAccountSnapshotAdapter(None),
            context=fixture.request.context,
            policy=StateReconciliationPolicy(),
        )


def test_portfolio_hash_mismatch_is_fatal() -> None:
    fixture = full_fixture(ranked=False)
    corrupted = fixture.portfolio_state.model_copy(update={"content_sha256": "f" * 64})
    with pytest.raises(HashMismatchError):
        run_module(
            portfolio_reader=StaticPortfolioStateReader(corrupted),
            account_port=StaticAccountSnapshotAdapter(None),
            context=fixture.request.context,
            policy=StateReconciliationPolicy(),
        )
