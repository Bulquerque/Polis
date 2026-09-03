"""P9.S8.M07 — off-policy evaluation and opportunity-cost diagnostics.

The baseline supports factual replay, IPS, self-normalized IPS, and doubly
robust estimation. No propensity is invented. Missing support returns an
explicit NOT_IDENTIFIABLE result.
"""

from __future__ import annotations

from statistics import fmean

import numpy as np
from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    EvidenceClass,
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import AttributionQuality


class LoggedPolicyObservation(StrictModel):
    observation_id: NonEmptyStr
    action_id: NonEmptyStr
    reward: float
    logging_propensity: float | None = Field(default=None, gt=0.0, le=1.0)
    target_action_probability: float = Field(ge=0.0, le=1.0)
    direct_model_chosen_reward: float | None = None
    direct_model_target_value: float | None = None
    evidence_class: EvidenceClass

    @model_validator(mode="after")
    def validate_direct_model(self) -> "LoggedPolicyObservation":
        if (self.direct_model_chosen_reward is None) != (
            self.direct_model_target_value is None
        ):
            raise ValueError("both direct-model values must be provided together")
        return self


class CounterfactualPolicy(StrictModel):
    minimum_observations: int = Field(default=10, ge=1)
    minimum_logging_propensity: float = Field(default=1e-3, gt=0.0, lt=1.0)
    maximum_importance_weight: float = Field(default=100.0, gt=1.0)
    minimum_effective_sample_size: float = Field(default=5.0, gt=0.0)


class OverlapDiagnostics(StrictModel):
    observation_count: int = Field(ge=0)
    supported_observation_count: int = Field(ge=0)
    minimum_logging_propensity: float | None = None
    maximum_importance_weight: float | None = None
    effective_sample_size: float | None = None
    support_qualified: bool


class CounterfactualPolicyResult(StrictModel):
    factual_mean_reward: float | None
    ips_value: float | None
    snips_value: float | None
    doubly_robust_value: float | None
    direct_model_value: float | None
    opportunity_cost_vs_factual: float | None
    overlap: OverlapDiagnostics
    quality: AttributionQuality
    evidence_class: EvidenceClass
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def evaluate_counterfactual_policy(
    observations: tuple[LoggedPolicyObservation, ...],
    policy: CounterfactualPolicy,
) -> CounterfactualPolicyResult:
    """Evaluate a target policy with explicit support and identifiability checks.

    IPS is the ordinary (Horvitz-Thompson) estimator and therefore divides by
    the total number of logged observations. Observations receiving zero target
    probability contribute zero but remain in the denominator. SNIPS keeps its
    separate self-normalized denominator.
    """

    reasons: set[str] = set()
    observation_count = len(observations)
    factual = fmean(item.reward for item in observations) if observations else None

    positive_target = [item for item in observations if item.target_action_probability > 0.0]
    supported = [
        item
        for item in positive_target
        if item.logging_propensity is not None
        and item.logging_propensity >= policy.minimum_logging_propensity
    ]
    if observation_count < policy.minimum_observations:
        reasons.add("P9_ATTRIBUTION_COUNTERFACTUAL_SAMPLE_INSUFFICIENT")

    missing_propensity = any(item.logging_propensity is None for item in positive_target)
    below_minimum_propensity = any(
        item.logging_propensity is not None
        and item.logging_propensity < policy.minimum_logging_propensity
        for item in positive_target
    )
    if missing_propensity:
        reasons.add("P9_ATTRIBUTION_PROPENSITY_MISSING")
    if below_minimum_propensity:
        reasons.add("P9_ATTRIBUTION_PROPENSITY_BELOW_MINIMUM")

    positive_weights = np.asarray(
        [
            item.target_action_probability / float(item.logging_propensity)
            for item in supported
        ],
        dtype=np.float64,
    )
    positive_rewards = np.asarray([item.reward for item in supported], dtype=np.float64)
    max_weight = float(np.max(positive_weights)) if positive_weights.size else None
    min_propensity = (
        min(float(item.logging_propensity) for item in supported) if supported else None
    )
    weight_sum = float(np.sum(positive_weights)) if positive_weights.size else 0.0
    weight_square_sum = (
        float(np.sum(positive_weights**2)) if positive_weights.size else 0.0
    )
    effective_sample_size = (
        weight_sum**2 / weight_square_sum if weight_square_sum > 0.0 else None
    )

    all_positive_supported = len(supported) == len(positive_target)
    support_qualified = bool(
        observation_count >= policy.minimum_observations
        and positive_target
        and all_positive_supported
        and max_weight is not None
        and max_weight <= policy.maximum_importance_weight
        and effective_sample_size is not None
        and effective_sample_size >= policy.minimum_effective_sample_size
        and not missing_propensity
        and not below_minimum_propensity
    )
    if not support_qualified:
        reasons.add("P9_ATTRIBUTION_SUPPORT_MISMATCH")

    weighted_reward_sum = (
        float(np.sum(positive_weights * positive_rewards))
        if positive_weights.size
        else 0.0
    )
    ips = (
        weighted_reward_sum / observation_count
        if support_qualified and observation_count > 0
        else None
    )
    snips = (
        weighted_reward_sum / weight_sum
        if support_qualified and weight_sum > 0.0
        else None
    )

    direct_complete = all(
        item.direct_model_target_value is not None
        and item.direct_model_chosen_reward is not None
        for item in observations
    )
    direct_rows = [
        item for item in observations if item.direct_model_target_value is not None
    ]
    direct_value = (
        fmean(float(item.direct_model_target_value) for item in direct_rows)
        if direct_rows
        else None
    )

    dr_value: float | None = None
    if support_qualified and direct_complete and observations:
        dr_terms: list[float] = []
        for item in observations:
            target_model = item.direct_model_target_value
            chosen_model = item.direct_model_chosen_reward
            if target_model is None or chosen_model is None:
                raise ValueError("complete direct-model values required for DR estimation")
            correction = 0.0
            if item.target_action_probability > 0.0:
                propensity = item.logging_propensity
                if propensity is None or propensity < policy.minimum_logging_propensity:
                    raise ValueError("qualified DR observation lacks valid support")
                correction = (
                    item.target_action_probability
                    / propensity
                    * (item.reward - chosen_model)
                )
            dr_terms.append(target_model + correction)
        dr_value = fmean(dr_terms)
    elif direct_rows and not direct_complete:
        reasons.add("P9_ATTRIBUTION_COUNTERFACTUAL_MODEL_INCOMPLETE")

    preferred_value = dr_value if dr_value is not None else snips
    if preferred_value is None and direct_value is not None:
        preferred_value = direct_value
        reasons.add("P9_ATTRIBUTION_COUNTERFACTUAL_MODEL_ONLY")
    opportunity = (
        preferred_value - factual
        if preferred_value is not None and factual is not None
        else None
    )

    if support_qualified and dr_value is not None:
        quality = AttributionQuality.QUALIFIED
        evidence = EvidenceClass.OBSERVABLE_COUNTERFACTUAL
    elif support_qualified:
        quality = AttributionQuality.LIMITED
        evidence = EvidenceClass.OBSERVABLE_COUNTERFACTUAL
    elif direct_value is not None:
        quality = AttributionQuality.LIMITED
        evidence = EvidenceClass.MODEL_BASED_COUNTERFACTUAL
    else:
        quality = AttributionQuality.NOT_IDENTIFIABLE
        evidence = EvidenceClass.UNAVAILABLE
        reasons.add("P9_ATTRIBUTION_COUNTERFACTUAL_NOT_IDENTIFIABLE")

    overlap = OverlapDiagnostics(
        observation_count=observation_count,
        supported_observation_count=len(supported),
        minimum_logging_propensity=min_propensity,
        maximum_importance_weight=max_weight,
        effective_sample_size=effective_sample_size,
        support_qualified=support_qualified,
    )
    payload = {
        "factual": factual,
        "ips": ips,
        "snips": snips,
        "dr": dr_value,
        "direct": direct_value,
        "opportunity": opportunity,
        "overlap": overlap.model_dump(mode="json"),
        "quality": quality,
        "evidence_class": evidence,
        "reason_codes": sorted(reasons),
    }
    return CounterfactualPolicyResult(
        factual_mean_reward=factual,
        ips_value=ips,
        snips_value=snips,
        doubly_robust_value=dr_value,
        direct_model_value=direct_value,
        opportunity_cost_vs_factual=opportunity,
        overlap=overlap,
        quality=quality,
        evidence_class=evidence,
        reason_codes=tuple(sorted(reasons)),
        result_sha256=payload_sha256(payload),
    )
