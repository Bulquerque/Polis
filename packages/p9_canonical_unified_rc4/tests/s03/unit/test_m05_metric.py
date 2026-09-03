from __future__ import annotations

from decimal import Decimal

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.errors import MetricPolicyError
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m05_competition_metric import (
    CompetitionMetricRegistry,
    compute_competition_score,
    validate_metric_parity,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.scoring_models import (
    CompetitionMetricPolicy,
    ComponentTransform,
    GoldenMetricExample,
    MetricComponentPolicy,
    MetricInputRecord,
    MissingComponentPolicy,
)

from tests.s03.conftest import ZERO_HASH


def metric_policy(**overrides):
    values = dict(
        metric_id="competition-demo",
        metric_version="1.0.0",
        components=(
            MetricComponentPolicy(component_id="return", weight=Decimal("1")),
            MetricComponentPolicy(component_id="risk", weight=Decimal("0.5"), transform=ComponentTransform.NEGATE),
        ),
        rounding_decimals=4,
    )
    values.update(overrides)
    return CompetitionMetricPolicy(**values)


def metric_input(components):
    return MetricInputRecord(
        trial_id="trial-1",
        fold_id="outer_000",
        configuration_id="config-1",
        qualification_sha256=ZERO_HASH,
        components=tuple(components),
        observation_count=10,
    )


def test_weighted_metric_is_exact_and_deterministic():
    policy = metric_policy()
    record = metric_input((("return", Decimal("0.10")), ("risk", Decimal("0.04"))))
    first = compute_competition_score(policy, record)
    second = compute_competition_score(policy, record)
    assert first.score == Decimal("0.0800")
    assert first == second


def test_clip_transform_is_applied_before_weight():
    policy = metric_policy(
        components=(
            MetricComponentPolicy(
                component_id="x",
                weight=Decimal("2"),
                transform=ComponentTransform.CLIP,
                clip_lower=Decimal("0"),
                clip_upper=Decimal("1"),
            ),
        )
    )
    result = compute_competition_score(policy, metric_input((("x", Decimal("3")),)))
    assert result.score == Decimal("2.0000")


def test_missing_component_fails_by_default():
    with pytest.raises(MetricPolicyError, match="METRIC_INPUT_MISSING"):
        compute_competition_score(metric_policy(), metric_input((("return", Decimal("0.1")),)))


def test_explicit_omit_and_renormalize_is_supported():
    policy = metric_policy(missing_policy=MissingComponentPolicy.OMIT_AND_RENORMALIZE)
    result = compute_competition_score(policy, metric_input((("return", Decimal("0.1")),)))
    assert result.score == Decimal("0.1500")


def test_registry_rejects_duplicate_policy_identity():
    registry = CompetitionMetricRegistry()
    policy = metric_policy()
    registry.register(policy)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(policy)
    assert registry.require("competition-demo", "1.0.0") == policy


def test_parity_report_passes_and_fails_examples():
    policy = metric_policy()
    report = validate_metric_parity(
        policy,
        (
            GoldenMetricExample(
                example_id="ok",
                inputs=(("return", Decimal("0.1")), ("risk", Decimal("0.04"))),
                expected_score=Decimal("0.0800"),
            ),
            GoldenMetricExample(
                example_id="bad",
                inputs=(("return", Decimal("0.1")), ("risk", Decimal("0.04"))),
                expected_score=Decimal("0.0900"),
            ),
        ),
    )
    assert report.passed is False
    assert [check.passed for check in report.checks] == [True, False]


def test_round_half_even_is_stable_at_boundary():
    policy = metric_policy(
        components=(MetricComponentPolicy(component_id="x", weight=Decimal("1")),),
        rounding_decimals=2,
    )
    result = compute_competition_score(policy, metric_input((("x", Decimal("1.005")),)))
    assert result.score == Decimal("1.00")
