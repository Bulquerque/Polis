from __future__ import annotations

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    EvidenceClass,
)
from quant_pipeline.phase_09.subphases.s08_attribution.contracts import (
    AttributionQuality,
)
from quant_pipeline.phase_09.subphases.s08_attribution.m07_counterfactual import (
    CounterfactualPolicy,
    LoggedPolicyObservation,
    evaluate_counterfactual_policy,
)


def _rows(
    n: int = 10,
    propensity: float = 1.0,
    target: float = 1.0,
    reward: float = 1.0,
    direct: bool = True,
) -> tuple[LoggedPolicyObservation, ...]:
    return tuple(
        LoggedPolicyObservation(
            observation_id=f"o{i}",
            action_id="a",
            reward=reward,
            logging_propensity=propensity,
            target_action_probability=target,
            direct_model_chosen_reward=reward if direct else None,
            direct_model_target_value=reward if direct else None,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        )
        for i in range(n)
    )


def test_doubly_robust_identity_policy() -> None:
    result = evaluate_counterfactual_policy(_rows(), CounterfactualPolicy())
    assert result.quality is AttributionQuality.QUALIFIED
    assert result.ips_value == 1.0
    assert result.snips_value == 1.0
    assert result.doubly_robust_value == 1.0
    assert result.opportunity_cost_vs_factual == 0.0


def test_missing_propensity_is_not_identifiable() -> None:
    rows = tuple(
        LoggedPolicyObservation(
            observation_id=f"o{i}",
            action_id="a",
            reward=1.0,
            logging_propensity=None,
            target_action_probability=1.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        )
        for i in range(10)
    )
    result = evaluate_counterfactual_policy(rows, CounterfactualPolicy())
    assert result.quality is AttributionQuality.NOT_IDENTIFIABLE
    assert "P9_ATTRIBUTION_PROPENSITY_MISSING" in result.reason_codes


def test_direct_model_only_is_limited() -> None:
    rows = tuple(
        LoggedPolicyObservation(
            observation_id=f"o{i}",
            action_id="a",
            reward=1.0,
            logging_propensity=None,
            target_action_probability=1.0,
            direct_model_chosen_reward=1.0,
            direct_model_target_value=2.0,
            evidence_class=EvidenceClass.MODEL_BASED_COUNTERFACTUAL,
        )
        for i in range(10)
    )
    result = evaluate_counterfactual_policy(rows, CounterfactualPolicy())
    assert result.quality is AttributionQuality.LIMITED
    assert result.direct_model_value == 2.0


def test_extreme_weights_fail_support() -> None:
    result = evaluate_counterfactual_policy(
        _rows(propensity=0.001, target=1.0),
        CounterfactualPolicy(
            maximum_importance_weight=10.0,
            minimum_logging_propensity=0.0001,
        ),
    )
    assert not result.overlap.support_qualified
    assert "P9_ATTRIBUTION_SUPPORT_MISMATCH" in result.reason_codes


def test_ips_uses_total_logged_population_denominator() -> None:
    rows = (
        LoggedPolicyObservation(
            observation_id="zero-target",
            action_id="a",
            reward=0.0,
            logging_propensity=None,
            target_action_probability=0.0,
            direct_model_chosen_reward=0.0,
            direct_model_target_value=0.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        ),
        LoggedPolicyObservation(
            observation_id="supported-target",
            action_id="a",
            reward=10.0,
            logging_propensity=1.0,
            target_action_probability=1.0,
            direct_model_chosen_reward=10.0,
            direct_model_target_value=10.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        ),
    )
    result = evaluate_counterfactual_policy(
        rows,
        CounterfactualPolicy(
            minimum_observations=2,
            minimum_effective_sample_size=0.5,
        ),
    )
    assert result.quality is AttributionQuality.QUALIFIED
    assert result.ips_value == 5.0
    assert result.snips_value == 10.0


def test_doubly_robust_allows_zero_target_row_without_propensity() -> None:
    rows = (
        LoggedPolicyObservation(
            observation_id="zero-target",
            action_id="a",
            reward=-100.0,
            logging_propensity=None,
            target_action_probability=0.0,
            direct_model_chosen_reward=-100.0,
            direct_model_target_value=2.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        ),
        LoggedPolicyObservation(
            observation_id="supported-target",
            action_id="a",
            reward=10.0,
            logging_propensity=1.0,
            target_action_probability=1.0,
            direct_model_chosen_reward=8.0,
            direct_model_target_value=8.0,
            evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        ),
    )
    result = evaluate_counterfactual_policy(
        rows,
        CounterfactualPolicy(
            minimum_observations=2,
            minimum_effective_sample_size=0.5,
        ),
    )
    assert result.quality is AttributionQuality.QUALIFIED
    assert result.doubly_robust_value == 6.0
