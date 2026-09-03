from __future__ import annotations

from decimal import Decimal

from .enums import ComparisonState, ReasonCode
from .models_shadow import ShadowEvaluationRequest, ShadowEvaluationResult


def _target_map(targets) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for target in targets:
        if target.instrument_id in result:
            raise ValueError("duplicate instrument_id in targets")
        result[target.instrument_id] = target.quantity
    return result


def _max_quantity_difference(request: ShadowEvaluationRequest) -> Decimal:
    champion = _target_map(request.champion.targets)
    challenger = _target_map(request.challenger.targets)
    instruments = set(champion) | set(challenger)
    return max((abs(champion.get(i, Decimal(0)) - challenger.get(i, Decimal(0))) for i in instruments), default=Decimal(0))


def run_shadow_evaluation(request: ShadowEvaluationRequest) -> ShadowEvaluationResult:
    champion, challenger = request.champion, request.challenger
    hashes_match = (
        champion.input_hash == challenger.input_hash
        and champion.scenario_hash == challenger.scenario_hash
        and champion.constraint_hash == challenger.constraint_hash
    )
    quantity_difference = _max_quantity_difference(request)
    risk_difference = abs(champion.predicted_risk - challenger.predicted_risk)
    action_agrees = champion.action == challenger.action
    reasons: list[ReasonCode] = []
    if not hashes_match:
        state = ComparisonState.INPUT_MISMATCH
        reasons.append(ReasonCode.CHALLENGER_INPUT_MISMATCH)
    elif challenger.predicted_risk > challenger.risk_limit:
        state = ComparisonState.UNSAFE_CHALLENGER
        reasons.append(ReasonCode.CHALLENGER_RISK_BREACH)
    elif quantity_difference > request.policy.material_quantity_tolerance or risk_difference > request.policy.risk_tolerance:
        state = ComparisonState.MATERIAL_DISAGREEMENT
        reasons.append(ReasonCode.MATERIAL_DECISION_DISAGREEMENT)
    elif not action_agrees or quantity_difference > request.policy.benign_quantity_tolerance:
        state = ComparisonState.BENIGN_DISAGREEMENT
    else:
        state = ComparisonState.AGREES
    return ShadowEvaluationResult(
        comparison_state=state,
        action_agrees=action_agrees,
        max_absolute_quantity_difference=quantity_difference,
        absolute_risk_difference=risk_difference,
        reason_codes=tuple(reasons),
        challenger_execution_authority=False,
    )
