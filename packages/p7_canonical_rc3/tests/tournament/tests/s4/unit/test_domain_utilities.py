from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_07_strategy_tournament.tournament.boundary.policy_records import (
    HeadPolicy,
    MetricBindingPolicy,
    PenaltyRule,
    ScoringPolicyContextRecord,
    ScoringPolicyRule,
)
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.enums import (
    MetricSourcePreference,
    MissingHeadAction,
    MissingMetricAction,
    NormalizationMethod,
    SmallGroupAction,
    TransformationMethod,
)
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.statistics import (
    average_percentile_rank,
    percentile,
    robust_location_scale,
    sigmoid,
)
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.transformations import normalize_value, transform_value
from quant_pipeline.phase_07_strategy_tournament.tournament.observability.events import DebugEvent


def _binding(**overrides):
    values = dict(
        metric_id="edge",
        source_preference=MetricSourcePreference.COMPARABLE_ONLY,
        transformation=TransformationMethod.IDENTITY,
        normalization=NormalizationMethod.ABSOLUTE_RANGE,
        metric_weight=1.0,
        absolute_lower=0.0,
        absolute_upper=1.0,
        min_group_size=2,
        small_group_action=SmallGroupAction.ABSOLUTE_FALLBACK,
        missing_metric_action=MissingMetricAction.BLOCK_HEAD,
    )
    values.update(overrides)
    return MetricBindingPolicy(**values)


def test_statistics_cover_interpolation_ties_and_bounds():
    with pytest.raises(ValueError):
        percentile((), 0.5)
    assert percentile((3.0,), 0.5) == 3.0
    assert percentile((1.0, 3.0, 5.0), 0.5) == 3.0
    assert percentile((0.0, 10.0), 0.25) == 2.5
    assert robust_location_scale((1.0, 2.0, 3.0, 4.0)) == (2.5, 1.5)
    assert average_percentile_rank(2.0, (2.0,)) == 0.5
    assert average_percentile_rank(2.0, (1.0, 2.0, 2.0, 4.0)) == pytest.approx(0.5)
    assert sigmoid(1000.0) > 0.999
    assert sigmoid(-1000.0) < 0.001


def test_transformations_cover_all_methods_and_invalid_bounds():
    assert transform_value(2.0, TransformationMethod.IDENTITY, None, None) == 2.0
    assert transform_value(-3.0, TransformationMethod.SIGNED_LOG1P, None, None) < 0.0
    assert transform_value(4.0, TransformationMethod.CLIP, 0.0, 1.0) == 1.0
    with pytest.raises(ValueError):
        transform_value(1.0, TransformationMethod.CLIP, None, 1.0)

    assert normalize_value(1.5, (1.5,), NormalizationMethod.IDENTITY_BOUNDED, None, None, 1.0) == 1.0
    assert normalize_value(5.0, (0.0, 5.0, 10.0), NormalizationMethod.ABSOLUTE_RANGE, 0.0, 10.0, 1.0) == 0.5
    assert normalize_value(5.0, (0.0, 5.0, 10.0), NormalizationMethod.PERCENTILE, None, None, 1.0) == 0.5
    assert normalize_value(2.0, (2.0, 2.0, 2.0), NormalizationMethod.ROBUST_Z_SIGMOID, None, None, 1.0) == 0.5
    assert normalize_value(4.0, (1.0, 2.0, 4.0), NormalizationMethod.ROBUST_Z_SIGMOID, None, None, 1.0) > 0.5
    with pytest.raises(ValueError):
        normalize_value(1.0, (1.0,), NormalizationMethod.ABSOLUTE_RANGE, 1.0, 1.0, 1.0)


def test_policy_models_fail_closed_on_ambiguous_or_invalid_configuration():
    with pytest.raises(ValidationError):
        _binding(clip_lower=1.0)
    with pytest.raises(ValidationError):
        _binding(clip_lower=2.0, clip_upper=1.0)
    with pytest.raises(ValidationError):
        _binding(absolute_lower=None, absolute_upper=None)

    binding = _binding()
    with pytest.raises(ValidationError):
        HeadPolicy(
            head_id="EDGE",
            head_weight=1.0,
            missing_head_action=MissingHeadAction.BLOCK,
            metric_bindings=(),
        )
    with pytest.raises(ValidationError):
        HeadPolicy(
            head_id="EDGE",
            head_weight=1.0,
            missing_head_action=MissingHeadAction.BLOCK,
            metric_bindings=(binding, binding),
        )
    head = HeadPolicy(
        head_id="EDGE",
        head_weight=1.0,
        missing_head_action=MissingHeadAction.BLOCK,
        metric_bindings=(binding,),
    )
    with pytest.raises(ValidationError):
        ScoringPolicyRule(rule_id="r", operational_modes=(), heads=(head,))
    with pytest.raises(ValidationError):
        ScoringPolicyRule(rule_id="r", operational_modes=("BASELINE",), heads=(head, head))
    with pytest.raises(ValidationError):
        ScoringPolicyRule(
            rule_id="r",
            operational_modes=("BASELINE",),
            heads=(head,),
            confidence_head_id="MISSING",
        )
    with pytest.raises(ValidationError):
        ScoringPolicyRule(
            rule_id="r",
            operational_modes=("BASELINE",),
            heads=(head,),
            penalty_rules=(PenaltyRule(penalty_id="p", head_id="MISSING", threshold=0.5, coefficient=1.0),),
        )
    rule = ScoringPolicyRule(rule_id="r", operational_modes=("BASELINE",), heads=(head,))
    with pytest.raises(ValidationError):
        ScoringPolicyContextRecord(
            policy_id="p",
            policy_version="1",
            operational_mode="BASELINE",
            rules=(rule, rule),
            forbidden_field_names=("future_return",),
        )
    with pytest.raises(ValidationError):
        ScoringPolicyContextRecord(
            policy_id="p",
            policy_version="1",
            operational_mode="BASELINE",
            rules=(rule,),
            forbidden_field_names=("future_return", "future_return"),
        )


def test_debug_event_is_strict_and_timezone_aware():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = DebugEvent(
        event_name="module_completed",
        timestamp=now,
        trace_id="trace",
        run_id="run",
        cycle_id="cycle",
        decision_time=now,
        module_id="P7.S4.M01",
        status="PASS",
    )
    assert event.counts == {}
    with pytest.raises(ValidationError):
        DebugEvent(
            event_name="bad",
            timestamp=datetime(2026, 1, 1),
            trace_id="trace",
            run_id="run",
            cycle_id="cycle",
            decision_time=now,
            module_id="P7.S4.M01",
            status="FAIL",
        )
