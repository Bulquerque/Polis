from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.errors import ContractError
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import (
    DecisionKind,
    NormalForecast,
    build_prequential_stream,
)

from tests.s07.conftest import outcome, prediction

pytestmark = pytest.mark.unit


def test_builds_matured_stream(base_time):
    issued = base_time - timedelta(days=2)
    pred = prediction("a", issued)
    result = build_prequential_stream((pred,), (outcome("a", issued, 0.25),))
    assert result.receipt.record_count == 1
    assert result.receipt.matured_count == 1
    assert result.records[0].active_outcome.value == 0.25


def test_duplicate_identical_event_is_idempotent(base_time):
    pred = prediction("a", base_time - timedelta(days=2))
    first = build_prequential_stream((pred,), ())
    second = build_prequential_stream((pred,), (), first.records)
    assert first.records == second.records
    assert first.receipt.stream_sha256 == second.receipt.stream_sha256


def test_conflicting_duplicate_rejected(base_time):
    issued = base_time - timedelta(days=2)
    left = prediction("same", issued)
    right = prediction(
        "same",
        issued,
        forecast=NormalForecast(mean=2.0, standard_deviation=1.0),
    )
    with pytest.raises(ContractError, match="DUPLICATE_CONFLICT"):
        build_prequential_stream((left, right), ())


def test_no_action_is_explicit(base_time):
    pred = prediction(
        "no-action",
        base_time - timedelta(days=2),
        decision_kind=DecisionKind.NO_ACTION,
    )
    result = build_prequential_stream((pred,), ())
    assert result.receipt.no_action_count == 1
    assert result.records[0].prediction.action_id is None


def test_outcome_revision_chain_selects_leaf(base_time):
    issued = base_time - timedelta(days=3)
    pred = prediction("revision", issued)
    old = outcome("revision", issued, 0.1, suffix="v1")
    new = outcome("revision", issued, 0.2, suffix="v2").model_copy(
        update={"supersedes_outcome_id": old.outcome_id}
    )
    result = build_prequential_stream((pred,), (old, new))
    assert result.records[0].active_outcome_id == new.outcome_id
