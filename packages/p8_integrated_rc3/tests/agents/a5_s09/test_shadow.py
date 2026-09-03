from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import (
    ChallengerDecision, ChampionDecision, RuntimeContext, ShadowEvaluationPolicy,
    ShadowEvaluationRequest, TargetQuantity,
)
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.enums import ComparisonState
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.shadow_evaluator import run_shadow_evaluation

H = "a"*64


def _decision(cls, *, action="HOLD", qty="1", risk="1", risk_limit="10", input_hash=H):
    return cls(policy_id=cls.__name__, input_hash=input_hash, scenario_hash=H, constraint_hash=H, action=action, targets=(TargetQuantity(instrument_id="X", quantity=Decimal(qty)),), predicted_risk=Decimal(risk), risk_limit=Decimal(risk_limit))


def _request(champion=None, challenger=None):
    context = RuntimeContext(run_id="r", cycle_id="c", trace_id="t", decision_time=datetime(2026,1,1,tzinfo=timezone.utc), observed_at=datetime(2026,1,1,0,1,tzinfo=timezone.utc), policy_version="v1")
    return ShadowEvaluationRequest(context=context, champion=champion or _decision(ChampionDecision), challenger=challenger or _decision(ChallengerDecision), policy=ShadowEvaluationPolicy(benign_quantity_tolerance=Decimal("0.1"), material_quantity_tolerance=Decimal("2"), risk_tolerance=Decimal("2")))


def test_agreement():
    assert run_shadow_evaluation(_request()).comparison_state is ComparisonState.AGREES


def test_input_mismatch():
    challenger = _decision(ChallengerDecision, input_hash="b"*64)
    assert run_shadow_evaluation(_request(challenger=challenger)).comparison_state is ComparisonState.INPUT_MISMATCH


def test_unsafe_challenger():
    challenger = _decision(ChallengerDecision, risk="11")
    assert run_shadow_evaluation(_request(challenger=challenger)).comparison_state is ComparisonState.UNSAFE_CHALLENGER


@pytest.mark.parametrize("qty,expected", [("1.05", ComparisonState.AGREES), ("1.5", ComparisonState.BENIGN_DISAGREEMENT), ("4", ComparisonState.MATERIAL_DISAGREEMENT)])
def test_quantity_disagreement(qty, expected):
    challenger = _decision(ChallengerDecision, qty=qty)
    assert run_shadow_evaluation(_request(challenger=challenger)).comparison_state is expected


def test_action_disagreement_is_benign_when_risk_close():
    challenger = _decision(ChallengerDecision, action="CLOSE")
    assert run_shadow_evaluation(_request(challenger=challenger)).comparison_state is ComparisonState.BENIGN_DISAGREEMENT


def test_challenger_cannot_have_execution_authority():
    with pytest.raises(ValidationError):
        ChallengerDecision(policy_id="x", input_hash=H, scenario_hash=H, constraint_hash=H, action="HOLD", targets=(), predicted_risk=Decimal(0), risk_limit=Decimal(1), execution_authority=True)


def test_duplicate_target_rejected_during_evaluation():
    challenger = _decision(ChallengerDecision).model_copy(update={"targets": (TargetQuantity(instrument_id="X", quantity=Decimal(1)), TargetQuantity(instrument_id="X", quantity=Decimal(2)))})
    with pytest.raises(ValueError, match="duplicate"):
        run_shadow_evaluation(_request(challenger=challenger))
