from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import build_prequential_stream
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m03_scoring import ScoringPolicy, score_prequential_records
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m06_sequential import (
    PairedLossObservation,
    SequentialComparisonPolicy,
    compare_policies_anytime,
)

from tests.s07.conftest import outcome, prediction

pytestmark = pytest.mark.property


def test_score_result_independent_of_input_order(base_time):
    predictions = tuple(
        prediction(f"p{i}", base_time - timedelta(days=3, minutes=i)) for i in range(4)
    )
    outcomes = tuple(outcome(item.event_id, item.issued_at, i / 10) for i, item in enumerate(predictions))
    forward = score_prequential_records(
        build_prequential_stream(predictions, outcomes).records,
        ScoringPolicy(),
    )
    reverse = score_prequential_records(
        build_prequential_stream(tuple(reversed(predictions)), tuple(reversed(outcomes))).records,
        ScoringPolicy(),
    )
    assert forward.score_panel_sha256 == reverse.score_panel_sha256


def test_comparing_policy_with_identical_losses_centers_at_zero():
    rows = tuple(
        PairedLossObservation(
            cohort_id=f"c{i}",
            prediction_event_id=f"p{i}",
            champion_policy_id="champion",
            challenger_policy_id="challenger",
            champion_loss=0.4,
            challenger_loss=0.4,
        )
        for i in range(50)
    )
    result = compare_policies_anytime(
        rows,
        SequentialComparisonPolicy(
            minimum_samples=10,
            loss_lower_bound=0.0,
            loss_upper_bound=1.0,
        ),
    )
    assert result.comparisons[0].mean_loss_difference == pytest.approx(0.0)
