from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from quant_pipeline.phase_08_portfolio_control.risk_state.api import run_s4
from quant_pipeline.phase_08_portfolio_control.risk_state.hashing import canonical_sha256


ROOT = Path(__file__).resolve().parents[3] / "schemas/s4"


def test_agent3_bundle_is_schema_valid_complete_and_non_executable(s4_request):
    result = run_s4(s4_request)
    payload = result.bundle.model_dump(mode="json")
    schema = json.loads(
        (ROOT / "P8DecisionReadyRiskBundle.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(payload)
    assert {item["candidate_id"] for item in payload["candidate_sizability"]} == {
        candidate.candidate_id for candidate in s4_request.candidates
    }
    forbidden = {"portfolio_weight", "target_quantity", "order", "expected_return"}
    assert forbidden.isdisjoint(payload)
    unhashed = result.bundle.model_dump(mode="python", exclude={"content_sha256"})
    assert canonical_sha256(unhashed) == result.bundle.content_sha256


def test_agent3_bundle_tampering_changes_hash(s4_request):
    result = run_s4(s4_request)
    payload = result.bundle.model_dump(mode="python", exclude={"content_sha256"})
    payload["cycle_id"] = "tampered"
    assert canonical_sha256(payload) != result.bundle.content_sha256
