from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import RuntimeAssuranceRequest


@pytest.fixture
def fixture_payload() -> dict:
    path = Path(__file__).parents[1] / "subphases/s09/fixtures/input/normal_request.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def normal_request(fixture_payload) -> RuntimeAssuranceRequest:
    return RuntimeAssuranceRequest.model_validate_json(json.dumps(fixture_payload))
