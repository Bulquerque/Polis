from datetime import UTC, datetime

from quant_pipeline.phase_09.subphases.s08_attribution.bundle import Clock
from quant_pipeline.phase_09.subphases.s08_attribution.runner import S8Pipeline

NOW=datetime(2026,1,5,12,0,tzinfo=UTC)


def test_replay_is_bitwise_deterministic(valid_request):
    first=S8Pipeline(Clock(lambda: NOW)).run(valid_request)
    second=S8Pipeline(Clock(lambda: NOW)).run(valid_request)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.integrity.payload_sha256 == second.integrity.payload_sha256
