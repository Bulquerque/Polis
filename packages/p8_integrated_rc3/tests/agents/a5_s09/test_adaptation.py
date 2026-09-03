from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import AdaptationBound, AdaptationKind, AdaptationRequest
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.bounded_adaptation import evaluate_adaptations
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.enums import AdaptationDecision, ReasonCode


@pytest.mark.parametrize("kind,old,new", [
    (AdaptationKind.INCREASE_LIQUIDITY_HAIRCUT, "0.1", "0.2"),
    (AdaptationKind.INCREASE_MARGIN_BUFFER, "0.1", "0.3"),
    (AdaptationKind.WIDEN_NO_TRADE_REGION, "1", "2"),
    (AdaptationKind.DECREASE_RISK_CAP, "1", "0.8"),
    (AdaptationKind.DECREASE_PARTICIPATION_RATE, "0.5", "0.2"),
    (AdaptationKind.ENTER_RESTRICTED_MODE, "0", "1"),
])
def test_conservative_adaptations(kind, old, new):
    req = AdaptationRequest(adaptation_id="a", kind=kind, previous_value=Decimal(old), proposed_value=Decimal(new), source_policy_id="p")
    bound = AdaptationBound(kind=kind, minimum_value=Decimal("0"), maximum_value=Decimal("10"))
    assert evaluate_adaptations((req,), (bound,))[0].decision is AdaptationDecision.ACCEPTED


@pytest.mark.parametrize("kind,old,new", [
    (AdaptationKind.INCREASE_LIQUIDITY_HAIRCUT, "0.2", "0.1"),
    (AdaptationKind.INCREASE_MARGIN_BUFFER, "0.3", "0.1"),
    (AdaptationKind.WIDEN_NO_TRADE_REGION, "2", "1"),
    (AdaptationKind.DECREASE_RISK_CAP, "0.8", "1"),
    (AdaptationKind.DECREASE_PARTICIPATION_RATE, "0.2", "0.5"),
])
def test_non_conservative_rejected(kind, old, new):
    req = AdaptationRequest(adaptation_id="a", kind=kind, previous_value=Decimal(old), proposed_value=Decimal(new), source_policy_id="p")
    bound = AdaptationBound(kind=kind, minimum_value=Decimal("0"), maximum_value=Decimal("10"))
    record = evaluate_adaptations((req,), (bound,))[0]
    assert ReasonCode.ADAPTATION_NON_CONSERVATIVE in record.reason_codes


def test_out_of_bounds_rejected():
    kind = AdaptationKind.INCREASE_MARGIN_BUFFER
    req = AdaptationRequest(adaptation_id="a", kind=kind, previous_value=Decimal("0.1"), proposed_value=Decimal("2"), source_policy_id="p")
    bound = AdaptationBound(kind=kind, minimum_value=Decimal("0"), maximum_value=Decimal("1"))
    record = evaluate_adaptations((req,), (bound,))[0]
    assert ReasonCode.ADAPTATION_OUT_OF_BOUNDS in record.reason_codes


def test_missing_bound_rejected():
    kind = AdaptationKind.INCREASE_MARGIN_BUFFER
    req = AdaptationRequest(adaptation_id="a", kind=kind, previous_value=Decimal("0.1"), proposed_value=Decimal("0.2"), source_policy_id="p")
    assert evaluate_adaptations((req,), ())[0].decision is AdaptationDecision.REJECTED


def test_duplicate_bound_rejected():
    kind = AdaptationKind.INCREASE_MARGIN_BUFFER
    bound = AdaptationBound(kind=kind, minimum_value=Decimal(0), maximum_value=Decimal(1))
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_adaptations((), (bound, bound))
