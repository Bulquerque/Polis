from __future__ import annotations

from quant_pipeline.phase_09.errors import InvariantViolation

from datetime import datetime

from .hashing import sha256_hex
from .m01_competition_objective_policy import build_competition_objective_policy
from .m02_robust_configuration_frontier import build_robust_configuration_frontier
from .m03_leaderboard_information_budget import assess_leaderboard_information_budget
from .m04_champion_challenger_qualification import qualify_champion_challengers
from .m05_promotion_recommendation import build_promotion_recommendation
from .m06_typed_feedback_builder import build_typed_feedback
from .m07_feedback_activation_gate import validate_feedback_for_future_activation
from .models.common import CycleRef
from .models.execution import (
    PromotionEvidenceInputBundle,
    S9ExecutionBundle,
    S9ExecutionEnvelope,
    S9ExecutionPolicy,
)


def run_s9_subphase(
    *,
    inputs: PromotionEvidenceInputBundle,
    created_at: datetime,
    policy: S9ExecutionPolicy | None = None,
) -> S9ExecutionEnvelope:
    """Execute P9.S9 deterministically without authorizing or activating changes."""

    policy = policy or S9ExecutionPolicy()
    source_cycle = inputs.source_context.cycle
    target_cycle = CycleRef(
        cycle_id=f"{source_cycle.cycle_id}+1",
        ordinal=source_cycle.ordinal + 1,
    )

    objective_result = build_competition_objective_policy(inputs.objective_spec)
    if objective_result.output is None:
        raise InvariantViolation("objective policy builder returned no output")
    frontier_result = build_robust_configuration_frontier(
        objective=objective_result.output,
        configurations=inputs.configurations,
        parameter_space=inputs.parameter_space,
        model_confidence_set_ids=inputs.model_confidence_set_ids,
        build_policy=policy.frontier,
    )
    if frontier_result.output is None:
        raise InvariantViolation("frontier builder returned no output")

    leaderboard_result, submission_eligibility = assess_leaderboard_information_budget(
        submission_ledger=inputs.submission_ledger,
        policy=inputs.leaderboard_policy,
        candidate_configuration_id=inputs.challenger_configuration_ids[0],
    )
    if leaderboard_result.output is None:
        raise InvariantViolation("leaderboard evaluator returned no output")
    qualification_result = qualify_champion_challengers(
        objective=objective_result.output,
        frontier=frontier_result.output,
        leaderboard=leaderboard_result.output,
        configurations=inputs.configurations,
        champion_configuration_id=inputs.champion_configuration_id,
        challenger_configuration_ids=inputs.challenger_configuration_ids,
        pairwise_evidence=inputs.pairwise_evidence,
    )
    if qualification_result.output is None:
        raise InvariantViolation("champion-challenger qualifier returned no output")
    promotion_result = build_promotion_recommendation(
        objective=objective_result.output,
        qualification=qualification_result.output,
        gate_receipts=inputs.promotion_gate_receipts,
        source_context=inputs.source_context,
        created_at=created_at,
    )
    feedback_result = build_typed_feedback(
        root_causes=inputs.root_causes,
        registry=inputs.feedback_policy_registry,
        previous_effectiveness=inputs.previous_feedback_effectiveness,
        source_cycle=source_cycle,
        target_cycle=target_cycle,
        policy=policy.feedback,
    )
    if feedback_result.output is None:
        raise InvariantViolation("typed feedback builder returned no output")
    activation_result = validate_feedback_for_future_activation(
        candidate_manifest=feedback_result.output,
        registry=inputs.feedback_policy_registry,
        target_capabilities=inputs.target_capabilities,
        previous_activation_ledger=inputs.previous_activation_ledger,
        current_cycle=source_cycle,
    )
    bundle = S9ExecutionBundle(
        source_context=inputs.source_context,
        objective_result=objective_result,
        frontier_result=frontier_result,
        leaderboard_result=leaderboard_result,
        submission_eligibility=submission_eligibility,
        qualification_result=qualification_result,
        promotion_result=promotion_result,
        feedback_result=feedback_result,
        activation_gate_result=activation_result,
        created_at=created_at,
    )
    return S9ExecutionEnvelope(payload=bundle, payload_sha256=sha256_hex(bundle))
