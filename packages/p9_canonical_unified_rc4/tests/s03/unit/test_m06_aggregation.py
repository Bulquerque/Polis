from __future__ import annotations

from decimal import Decimal

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m06_score_aggregation import aggregate_scores
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.scoring_models import (
    CompetitionScoreRecord,
    FoldWeightPolicy,
    ScoreAggregationPolicy,
    ScoreContext,
)

from tests.s03.conftest import ZERO_HASH


def score(config: str, fold: str, value: str, observations: int = 10):
    return CompetitionScoreRecord(
        metric_id="metric",
        metric_version="1.0.0",
        trial_id=f"{config}:{fold}",
        fold_id=fold,
        configuration_id=config,
        score=Decimal(value),
        components=(),
        observation_count=observations,
        policy_sha256=ZERO_HASH,
        content_sha256=ZERO_HASH,
    )


def contexts():
    return (
        ScoreContext(score=score("a", "f1", "1"), cohort_id="c"),
        ScoreContext(score=score("a", "f2", "3"), cohort_id="c"),
        ScoreContext(score=score("b", "f1", "0"), cohort_id="c"),
        ScoreContext(score=score("b", "f2", "2"), cohort_id="c"),
    )


def test_equal_fold_aggregation_and_loss_sign():
    result = aggregate_scores(
        contexts(),
        ScoreAggregationPolicy(policy_id="agg", minimum_fold_coverage=Decimal("1")),
        expected_fold_ids=("f1", "f2"),
    )
    by_id = {item.configuration_id: item for item in result.aggregates}
    assert by_id["a"].mean_score == Decimal("2")
    assert by_id["a"].median_score == Decimal("2")
    assert by_id["a"].worst_score == Decimal("1")
    losses = {(item.configuration_id, item.unit_id): item.loss for item in result.loss_series}
    assert losses[("a", "f1")] == Decimal("-1")


def test_observation_weighting_changes_weighted_mean_only():
    records = (
        ScoreContext(score=score("a", "f1", "1", observations=1), cohort_id="c"),
        ScoreContext(score=score("a", "f2", "3", observations=3), cohort_id="c"),
    )
    result = aggregate_scores(
        records,
        ScoreAggregationPolicy(
            policy_id="agg",
            weight_policy=FoldWeightPolicy.OBSERVATION_COUNT,
            minimum_fold_coverage=Decimal("1"),
        ),
        expected_fold_ids=("f1", "f2"),
    )
    aggregate = result.aggregates[0]
    assert aggregate.mean_score == Decimal("2")
    assert aggregate.weighted_mean_score == Decimal("2.5")


def test_low_coverage_is_explicit():
    result = aggregate_scores(
        (ScoreContext(score=score("a", "f1", "1"), cohort_id="c"),),
        ScoreAggregationPolicy(policy_id="agg", minimum_fold_coverage=Decimal("1")),
        expected_fold_ids=("f1", "f2"),
    )
    assert result.aggregates[0].status == "INSUFFICIENT_EVIDENCE"
    assert "P9_S3_INSUFFICIENT_FOLD_COVERAGE" in result.reason_codes


def test_duplicate_fold_for_configuration_is_rejected():
    duplicate = (
        ScoreContext(score=score("a", "f1", "1"), cohort_id="c"),
        ScoreContext(score=score("a", "f1", "2"), cohort_id="c"),
    )
    with pytest.raises(ValueError, match="duplicate"):
        aggregate_scores(
            duplicate,
            ScoreAggregationPolicy(policy_id="agg"),
            expected_fold_ids=("f1",),
        )


def test_permutation_invariance():
    first = aggregate_scores(
        contexts(),
        ScoreAggregationPolicy(policy_id="agg"),
        expected_fold_ids=("f1", "f2"),
    )
    second = aggregate_scores(
        tuple(reversed(contexts())),
        ScoreAggregationPolicy(policy_id="agg"),
        expected_fold_ids=("f1", "f2"),
    )
    assert first == second


def test_invalid_observation_weights_are_rejected():
    records = (
        ScoreContext(score=score("a", "f1", "1", observations=0), cohort_id="c"),
    )
    with pytest.raises(ValueError, match="WEIGHT_POLICY_INVALID"):
        aggregate_scores(
            records,
            ScoreAggregationPolicy(policy_id="agg", weight_policy=FoldWeightPolicy.OBSERVATION_COUNT),
            expected_fold_ids=("f1",),
        )
