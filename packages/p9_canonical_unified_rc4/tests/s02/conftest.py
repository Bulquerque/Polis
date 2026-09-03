from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import FixedClock
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.request import S2RunRequest
from quant_pipeline.phase_09.subphases.s02_experiment_governance.runner import S2Runner

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "s01_s02" / "s2" / "full" / "s2_request.json"


def raw_request() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def parse_request(raw: dict[str, Any] | None = None) -> S2RunRequest:
    return (
        S2RunRequest.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
        if raw is None
        else S2RunRequest.model_validate_json(json.dumps(raw))
    )


@pytest.fixture
def s2_request() -> S2RunRequest:
    return parse_request()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 1, 7, 15, 0, tzinfo=UTC))


@pytest.fixture
def result(s2_request: S2RunRequest, clock: FixedClock):
    return S2Runner(clock=clock).run(s2_request)
