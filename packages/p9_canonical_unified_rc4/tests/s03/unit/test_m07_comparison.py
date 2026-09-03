from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.comparison_models import (
    ComparisonPolicy,
    ConfigurationLineage,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m07_provisional_mcs import compare_trials
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.scoring_models import (
    ComparisonLossRecord,
    ConfigurationScoreAggregate,
)

from tests.s03.conftest import ZERO_HASH


def aggregate(config: str, mean: str = "0"):
    return ConfigurationScoreAggregate(
        configuration_id=config,
        cohort_id="c",
        fold_count=2,
        expected_fold_count=2,
        coverage=Decimal("1"),
        mean_score=Decimal(mean),
        median_score=Decimal(mean),
        worst_score=Decimal(mean),
        score_std=Decimal("0"),
        weighted_mean_score=Decimal(mean),
        status="QUALIFIED",
    )


def lineage(*items):
    return tuple(
        ConfigurationLineage(configuration_id=config, economic_fingerprint=fingerprint)
        for config, fingerprint in items
    )


def losses(config: str, values):
    return tuple(
        ComparisonLossRecord(configuration_id=config, cohort_id="c", unit_id=f"f{i}", loss=Decimal(value))
        for i, value in enumerate(values, 1)
    )


def test_clear_dominance_removes_worse_configuration():
    result = compare_trials(
        (aggregate("a"), aggregate("b")),
        losses("a", ("1", "1")) + losses("b", ("2", "2")),
        lineage(("a", "a" * 64), ("b", "b" * 64)),
        ComparisonPolicy(policy_id="cmp", minimum_common_units=2),
        cohort_id="c",
    )
    assert result.non_dominated_configuration_ids == ("a",)
    assert result.provisional_model_set.configuration_ids == ("a",)
    assert "P9_S3_PROVISIONAL_ONLY" in result.reason_codes


def test_equivalent_economic_configurations_are_grouped():
    fingerprint = "a" * 64
    result = compare_trials(
        (aggregate("a"), aggregate("a-copy"), aggregate("b")),
        losses("a", ("1", "1")) + losses("a-copy", ("1", "1")) + losses("b", ("2", "2")),
        lineage(("a", fingerprint), ("a-copy", fingerprint), ("b", "b" * 64)),
        ComparisonPolicy(policy_id="cmp"),
        cohort_id="c",
    )
    group = next(group for group in result.equivalence_groups if group.economic_fingerprint == fingerprint)
    assert group.configuration_ids == ("a", "a-copy")


def test_incompatible_units_are_not_compared():
    result = compare_trials(
        (aggregate("a"), aggregate("b")),
        losses("a", ("1", "1")) + (
            ComparisonLossRecord(configuration_id="b", cohort_id="c", unit_id="other", loss=Decimal("2")),
        ),
        lineage(("a", "a" * 64), ("b", "b" * 64)),
        ComparisonPolicy(policy_id="cmp", minimum_common_units=2),
        cohort_id="c",
    )
    assert result.pairwise[0].comparable is False
    assert "P9_S3_COMPARISON_NOT_IDENTIFIABLE" in result.reason_codes


def test_single_configuration_is_explicitly_insufficient():
    result = compare_trials(
        (aggregate("a"),),
        losses("a", ("1", "1")),
        lineage(("a", "a" * 64)),
        ComparisonPolicy(policy_id="cmp"),
        cohort_id="c",
    )
    assert "P9_S3_INSUFFICIENT_CONFIGURATIONS" in result.reason_codes
    assert result.provisional_model_set.configuration_ids == ("a",)


def test_mean_loss_tolerance_keeps_near_best_non_dominated_models():
    result = compare_trials(
        (aggregate("a"), aggregate("b")),
        losses("a", ("1.0", "1.2")) + losses("b", ("1.05", "1.16")),
        lineage(("a", "a" * 64), ("b", "b" * 64)),
        ComparisonPolicy(policy_id="cmp", mean_loss_tolerance=Decimal("0.05")),
        cohort_id="c",
    )
    assert set(result.provisional_model_set.configuration_ids) == {"a", "b"}


def test_order_invariance():
    args = (
        (aggregate("a"), aggregate("b")),
        losses("a", ("1", "1")) + losses("b", ("2", "2")),
        lineage(("a", "a" * 64), ("b", "b" * 64)),
    )
    first = compare_trials(*args, ComparisonPolicy(policy_id="cmp"), cohort_id="c")
    second = compare_trials(
        tuple(reversed(args[0])),
        tuple(reversed(args[1])),
        tuple(reversed(args[2])),
        ComparisonPolicy(policy_id="cmp"),
        cohort_id="c",
    )
    assert first == second
