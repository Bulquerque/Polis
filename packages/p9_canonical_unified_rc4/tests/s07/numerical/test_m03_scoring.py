from __future__ import annotations

from datetime import timedelta
from math import pi, sqrt

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import (
    BinaryProbabilityForecast,
    NormalForecast,
    build_prequential_stream,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m03_scoring import (
    ScoringPolicy,
    score_prequential_records,
)

from tests.s07.conftest import outcome, prediction

pytestmark = pytest.mark.numerical


def test_brier_score_known_example(base_time):
    issued = base_time - timedelta(days=2)
    pred = prediction("binary", issued, forecast=BinaryProbabilityForecast(probability=0.8))
    stream = build_prequential_stream((pred,), (outcome("binary", issued, 1.0),))
    result = score_prequential_records(stream.records, ScoringPolicy(minimum_calibration_count=2))
    brier = next(item.score_value for item in result.score_records if item.score_name == "BRIER")
    assert brier == pytest.approx(0.04)


def test_normal_crps_at_mean(base_time):
    issued = base_time - timedelta(days=2)
    pred = prediction("normal", issued, forecast=NormalForecast(mean=0.0, standard_deviation=1.0))
    stream = build_prequential_stream((pred,), (outcome("normal", issued, 0.0),))
    result = score_prequential_records(stream.records, ScoringPolicy())
    crps = next(item.score_value for item in result.score_records if item.score_name == "NORMAL_CRPS")
    expected = (sqrt(2.0) - 1.0) / sqrt(pi)
    assert crps == pytest.approx(expected)


def test_zero_probability_contradiction_is_invalid(base_time):
    issued = base_time - timedelta(days=2)
    pred = prediction("zero", issued, forecast=BinaryProbabilityForecast(probability=0.0))
    stream = build_prequential_stream((pred,), (outcome("zero", issued, 1.0),))
    result = score_prequential_records(stream.records, ScoringPolicy())
    log_score = next(item for item in result.score_records if item.score_name == "LOG_LOSS")
    assert log_score.score_value is None
    assert log_score.quality_state == "INVALID"
