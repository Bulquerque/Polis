"""P8.S3.M06 ambiguity and actionability compiler."""
from __future__ import annotations

import numpy as np

from ..arrays import ScenarioSet
from ..contracts import (
    ActionabilityPolicy, ActionabilityState, AmbiguityAssessment, QualityAssessment,
    QualityStatus, ReductionAssessment, ReductionStatus,
)

MODULE_ID = "P8.S3.M06"


def _quality_penalty(quality: QualityAssessment) -> float:
    status_penalties = {
        QualityStatus.FULLY_QUALIFIED: 0.0,
        QualityStatus.QUALIFIED_WITH_HAIRCUT: 0.25,
        QualityStatus.TAIL_INCOMPLETE: 0.60,
        QualityStatus.PATH_INCOMPLETE: 0.60,
        QualityStatus.REGIME_INCOMPLETE: 0.50,
        QualityStatus.DECISION_UNSTABLE: 0.80,
        QualityStatus.NOT_ACTIONABLE: 1.0,
    }
    return max(status_penalties[status] for status in quality.status_by_family.values())


def compile_ambiguity(
    scenarios: ScenarioSet,
    quality: QualityAssessment,
    reduction: ReductionAssessment,
    calibration_score: float | None,
    ood_score: float | None,
    disagreement_score: float | None,
    ordinal_risk_cap: float | None,
    policy: ActionabilityPolicy,
) -> AmbiguityAssessment:
    sources = [
        1.0-quality.score,
        _quality_penalty(quality),
        1.0-calibration_score if calibration_score is not None else 0.50,
        ood_score if ood_score is not None else 0.50,
        disagreement_score if disagreement_score is not None else 0.50,
        1.0 if reduction.status == ReductionStatus.SCENARIO_REDUCTION_UNSAFE else 0.0,
    ]
    uncertainty = float(np.clip(max(sources), 0.0, 1.0))
    effective_quality = 1.0-uncertainty
    risk_cap = float(np.clip(effective_quality, 0.0, 1.0))
    if ordinal_risk_cap is not None:
        risk_cap = min(risk_cap, ordinal_risk_cap)
    ambiguity_radius = uncertainty * policy.max_ambiguity_radius
    liquidity_haircut = uncertainty * policy.max_liquidity_haircut
    margin_buffer = uncertainty * policy.max_margin_buffer
    if effective_quality >= policy.nominal_quality_floor and uncertainty < 0.20:
        state = ActionabilityState.NOMINAL_ACTIONABLE
    elif effective_quality >= policy.nominal_quality_floor:
        state = ActionabilityState.ROBUST_ONLY
    elif effective_quality >= policy.degraded_quality_floor:
        state = ActionabilityState.DEGRADED_ACTIONABLE
    elif effective_quality >= policy.no_new_risk_floor:
        state = ActionabilityState.NO_NEW_RISK
        risk_cap = 0.0
    else:
        state = ActionabilityState.NO_ACTION_VALID
        risk_cap = 0.0
    probabilities = scenarios.probabilities
    band = ambiguity_radius / max(len(probabilities), 1)
    lower = np.clip(probabilities-band, 0.0, 1.0)
    upper = np.clip(probabilities+band, 0.0, 1.0)
    reasons: list[str] = []
    if reduction.status == ReductionStatus.SCENARIO_REDUCTION_UNSAFE:
        reasons.append("SCENARIO_REDUCTION_UNSAFE")
    if ood_score is None:
        reasons.append("OOD_EVIDENCE_UNAVAILABLE")
    if disagreement_score is None:
        reasons.append("DISAGREEMENT_EVIDENCE_UNAVAILABLE")
    return AmbiguityAssessment(
        actionability_state=state, uncertainty_score=uncertainty,
        ambiguity_radius=ambiguity_radius, risk_budget_cap=risk_cap,
        liquidity_haircut=liquidity_haircut, margin_buffer=margin_buffer,
        probability_lower_bounds=tuple(float(x) for x in lower),
        probability_upper_bounds=tuple(float(x) for x in upper),
        reason_codes=tuple(reasons),
    )
