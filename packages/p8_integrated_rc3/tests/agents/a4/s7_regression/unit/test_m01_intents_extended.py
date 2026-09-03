from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.agents.a4.conftest import NOW, make_bundle
from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import (
    CandidateAllocation,
    CurrentPosition,
    CurrentVirtualPosition,
    ExecutableTarget,
    seal_execution_authorization_bundle,
)
from quant_pipeline.phase_08_portfolio_control.foundation.enums import IntentType, PositionIntent
from quant_pipeline.phase_08_portfolio_control.foundation.errors import (
    AuthorizationError,
    ContractIntegrityError,
    TemporalIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.policies import IntentPolicy


def _target_with_allocation(stock_bundle, quantity: Decimal, allocations: tuple[CandidateAllocation, ...]):
    target = stock_bundle.targets[0].model_copy(update={
        "target_quantity": quantity,
        "virtual_allocations": allocations,
    })
    return target


def test_hash_tampering_is_fatal(stock_bundle, context):
    tampered = stock_bundle.model_copy(update={"content_sha256": "f" * 64})
    with pytest.raises(ContractIntegrityError):
        m01_intents.execute(tampered, context, IntentPolicy())


def test_decision_time_mismatch_is_fatal(stock_bundle, context):
    changed_context = context.model_copy(update={"decision_time": context.decision_time + timedelta(seconds=1)})
    with pytest.raises(TemporalIntegrityError):
        m01_intents.execute(stock_bundle, changed_context, IntentPolicy())


def test_increase_from_existing_long_uses_virtual_delta(stock_bundle, stock_instrument, context):
    target = _target_with_allocation(
        stock_bundle, Decimal("10"),
        (CandidateAllocation(candidate_id="c1", allocated_target_quantity=Decimal("10")),),
    )
    bundle = make_bundle(
        (target,), stock_bundle.authorizations, (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("5")),),
        virtual_positions=(CurrentVirtualPosition(candidate_id="c1", instrument_id="AAPL", quantity=Decimal("5")),),
    )
    result = m01_intents.execute(bundle, context, IntentPolicy())
    intent = result.intents[0]
    assert intent.intent_type == IntentType.INCREASE
    assert intent.position_intent == PositionIntent.BUY_TO_OPEN
    assert intent.quantity == Decimal("5")
    assert intent.virtual_allocations[0].allocated_target_quantity == Decimal("5")


def test_close_existing_long(stock_bundle, stock_instrument, context):
    target = _target_with_allocation(stock_bundle, Decimal("0"), ())
    bundle = make_bundle(
        (target,), stock_bundle.authorizations, (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("5")),),
        virtual_positions=(CurrentVirtualPosition(candidate_id="c1", instrument_id="AAPL", quantity=Decimal("5")),),
    )
    result = m01_intents.execute(bundle, context, IntentPolicy())
    intent = result.intents[0]
    assert intent.intent_type == IntentType.CLOSE
    assert intent.position_intent == PositionIntent.SELL_TO_CLOSE
    assert intent.signed_quantity == Decimal("-5")
    assert intent.virtual_allocations[0].allocated_target_quantity == Decimal("-5")


def test_zero_crossing_requires_new_cycle(stock_bundle, stock_instrument, context):
    target = _target_with_allocation(
        stock_bundle, Decimal("-5"),
        (CandidateAllocation(candidate_id="c1", allocated_target_quantity=Decimal("-5")),),
    )
    bundle = make_bundle(
        (target,), stock_bundle.authorizations, (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("5")),),
        virtual_positions=(CurrentVirtualPosition(candidate_id="c1", instrument_id="AAPL", quantity=Decimal("5")),),
    )
    with pytest.raises(AuthorizationError, match="zero-crossing"):
        m01_intents.execute(bundle, context, IntentPolicy())


def test_virtual_only_reallocation_is_preserved(stock_bundle, stock_instrument, context):
    target = _target_with_allocation(
        stock_bundle, Decimal("10"),
        (
            CandidateAllocation(candidate_id="c1", allocated_target_quantity=Decimal("4")),
            CandidateAllocation(candidate_id="c2", allocated_target_quantity=Decimal("6")),
        ),
    )
    bundle = make_bundle(
        (target,), stock_bundle.authorizations, (stock_instrument,),
        positions=(CurrentPosition(instrument_id="AAPL", quantity=Decimal("10")),),
        virtual_positions=(CurrentVirtualPosition(candidate_id="c1", instrument_id="AAPL", quantity=Decimal("10")),),
    )
    result = m01_intents.execute(bundle, context, IntentPolicy())
    assert result.intents == ()
    assert result.no_action is False
    assert {(x.candidate_id, x.signed_quantity_delta) for x in result.virtual_reallocations} == {
        ("c1", Decimal("-6")), ("c2", Decimal("6"))
    }


def test_invalid_contract_at_decision_is_rejected(stock_bundle, stock_instrument, context):
    invalid = stock_instrument.model_copy(update={"valid_until": NOW - timedelta(seconds=1)})
    bundle = make_bundle(stock_bundle.targets, stock_bundle.authorizations, (invalid,))
    with pytest.raises(AuthorizationError, match="instrument contract not valid"):
        m01_intents.execute(bundle, context, IntentPolicy())
