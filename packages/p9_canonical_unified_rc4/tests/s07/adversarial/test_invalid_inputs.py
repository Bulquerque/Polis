from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s07_prospective_validation.errors import TemporalIntegrityError
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import (
    OutcomeEvent,
    QuantileForecast,
    QuantilePoint,
    build_prequential_stream,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import EvidenceClass, MaturityState

from tests.s07.conftest import prediction

pytestmark = pytest.mark.adversarial


def test_crossing_quantiles_rejected():
    with pytest.raises(ValidationError, match="nondecreasing"):
        QuantileForecast(
            points=(
                QuantilePoint(quantile=0.1, value=1.0),
                QuantilePoint(quantile=0.9, value=0.0),
            )
        )


def test_outcome_available_before_prediction_rejected(base_time):
    pred = prediction("p", base_time)
    bad = OutcomeEvent(
        outcome_id="o",
        prediction_event_id="p",
        observed_at=base_time - timedelta(minutes=2),
        available_at=base_time - timedelta(minutes=1),
        maturity_state=MaturityState.MATURED,
        evidence_class=EvidenceClass.FACTUAL_EXECUTED,
        value=1.0,
        vintage_id="v1",
    )
    with pytest.raises(TemporalIntegrityError, match="TEMPORAL"):
        build_prequential_stream((pred,), (bad,))
