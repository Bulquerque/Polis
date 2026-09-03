from __future__ import annotations

import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.runner import Clock, S7Pipeline

pytestmark = pytest.mark.replay


def test_same_request_and_clock_reproduce_bundle_hash(base_time, full_request):
    first = S7Pipeline(clock=Clock(lambda: base_time)).run(full_request)
    second = S7Pipeline(clock=Clock(lambda: base_time)).run(full_request)
    assert first.integrity.payload_sha256 == second.integrity.payload_sha256
    assert first == second
