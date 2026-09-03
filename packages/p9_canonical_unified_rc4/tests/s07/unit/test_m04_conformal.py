from __future__ import annotations

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import Availability
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m04_conformal import (
    ConformalObservation,
    ConformalPolicy,
    monitor_adaptive_conformal,
)

pytestmark = pytest.mark.unit


def test_miss_decreases_miscoverage_and_widens_future_layer():
    policy = ConformalPolicy(target_coverage=0.9, learning_rate=0.05, minimum_group_count=2)
    observations = (
        ConformalObservation(event_id="a", group_id="g", lower=-1.0, upper=1.0, outcome=0.0),
        ConformalObservation(event_id="b", group_id="g", lower=-1.0, upper=1.0, outcome=3.0),
    )
    result = monitor_adaptive_conformal(observations, policy)
    assert result.steps[1].alpha_after < result.steps[1].alpha_before
    assert result.summaries[0].empirical_coverage == pytest.approx(0.5)


def test_unavailable_capability_is_explicit():
    policy = ConformalPolicy(
        availability=Availability.UNAVAILABLE,
        target_coverage=0.9,
        learning_rate=0.05,
    )
    result = monitor_adaptive_conformal((), policy)
    assert result.availability is Availability.UNAVAILABLE
    assert "P9_LIVE_CONFORMAL_CAPABILITY_UNAVAILABLE" in result.limitations


def test_excessive_width_limits_qualification():
    policy = ConformalPolicy(
        target_coverage=0.9,
        learning_rate=0.05,
        minimum_group_count=2,
        maximum_qualified_width=1.0,
    )
    observations = tuple(
        ConformalObservation(event_id=str(i), group_id="g", lower=-5.0, upper=5.0, outcome=0.0)
        for i in range(2)
    )
    result = monitor_adaptive_conformal(observations, policy)
    assert result.summaries[0].quality_state == "LIMITED"
    assert "P9_LIVE_CONFORMAL_INTERVAL_UNUSABLE" in result.summaries[0].reason_codes
