from datetime import timedelta
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import seal_execution_authorization_bundle

from quant_pipeline.phase_08_portfolio_control.foundation.errors import AuthorizationError
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.policies import IntentPolicy


def test_builds_buy_open_intent(stock_bundle, context):
    result = m01_intents.execute(stock_bundle, context, IntentPolicy())
    assert len(result.intents) == 1
    assert result.intents[0].signed_quantity == Decimal("10")
    assert result.intents[0].position_intent.value == "BUY_TO_OPEN"
    assert result.no_action is False


def test_open_order_effect_prevents_duplicate(stock_bundle, context):
    from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import CandidateAllocation, OpenOrderExposure
    changed = seal_execution_authorization_bundle(stock_bundle.model_copy(update={
        "open_orders": (OpenOrderExposure(order_id="o", instrument_id="AAPL", remaining_signed_quantity=Decimal("10"), virtual_allocations=(CandidateAllocation(candidate_id="c1", allocated_target_quantity=Decimal("10")),)),)
    }))
    result = m01_intents.execute(changed, context, IntentPolicy())
    assert result.no_action is True


def test_expired_authorization_rejected(stock_bundle, context):
    auth = stock_bundle.authorizations[0].model_copy(update={"valid_until": context.decision_time})
    changed = seal_execution_authorization_bundle(stock_bundle.model_copy(update={"authorizations": (auth,)}))
    with pytest.raises(AuthorizationError):
        m01_intents.execute(changed, context, IntentPolicy())


def test_deterministic_intent_hash(stock_bundle, context):
    a = m01_intents.execute(stock_bundle, context, IntentPolicy())
    b = m01_intents.execute(stock_bundle, context, IntentPolicy())
    assert a == b
