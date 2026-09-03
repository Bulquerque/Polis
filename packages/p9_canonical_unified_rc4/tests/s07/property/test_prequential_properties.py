from __future__ import annotations

from datetime import timedelta
import itertools

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.m01_prequential import build_prequential_stream

from tests.s07.conftest import outcome, prediction

pytestmark = pytest.mark.property


def test_permutation_invariance(base_time):
    predictions = tuple(
        prediction(f"p{i}", base_time - timedelta(days=3, hours=i)) for i in range(3)
    )
    outcomes = tuple(
        outcome(item.event_id, item.issued_at, float(index))
        for index, item in enumerate(predictions)
    )
    hashes = set()
    for pred_perm in itertools.permutations(predictions):
        for outcome_perm in itertools.permutations(outcomes):
            hashes.add(build_prequential_stream(pred_perm, outcome_perm).receipt.stream_sha256)
    assert len(hashes) == 1


def test_future_event_does_not_change_past_record(base_time):
    past = prediction("past", base_time - timedelta(days=4))
    past_outcome = outcome("past", past.issued_at, 1.0)
    initial = build_prequential_stream((past,), (past_outcome,))
    future = prediction("future", base_time + timedelta(days=1))
    expanded = build_prequential_stream((past, future), (past_outcome,))
    assert initial.records[0] == expanded.records[0]
