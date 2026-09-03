from __future__ import annotations

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.m06_sequential import (
    ComparisonState,
    PairedLossObservation,
    SequentialComparisonPolicy,
    compare_policies_anytime,
)

pytestmark = pytest.mark.numerical


def observations(challenger_loss: float, count: int = 120):
    return tuple(
        PairedLossObservation(
            cohort_id=f"c{i}",
            prediction_event_id=f"p{i}",
            champion_policy_id="champion",
            challenger_policy_id="challenger",
            champion_loss=0.6,
            challenger_loss=challenger_loss,
        )
        for i in range(count)
    )


def policy():
    return SequentialComparisonPolicy(
        alpha=0.05,
        minimum_samples=20,
        minimum_effect=0.01,
        loss_lower_bound=0.0,
        loss_upper_bound=1.0,
    )


def test_challenger_superior_when_loss_is_materially_lower():
    result = compare_policies_anytime(observations(0.1), policy())
    comparison = result.comparisons[0]
    assert comparison.state is ComparisonState.CHALLENGER_SUPERIOR
    assert "challenger" in result.retained_policy_ids


def test_champion_superior_when_challenger_loss_is_higher():
    result = compare_policies_anytime(observations(0.95), policy())
    assert result.comparisons[0].state is ComparisonState.CHAMPION_SUPERIOR


def test_insufficient_evidence_is_explicit():
    result = compare_policies_anytime(observations(0.1, count=5), policy())
    assert result.comparisons[0].state is ComparisonState.INSUFFICIENT_EVIDENCE


def test_same_losses_never_claim_superiority():
    result = compare_policies_anytime(observations(0.6), policy())
    assert result.comparisons[0].state is ComparisonState.STATISTICALLY_INDISTINGUISHABLE
