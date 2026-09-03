import json
from copy import deepcopy
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import RuntimeAssuranceRequest, run_runtime_assurance
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.invariant_monitor import run_invariant_monitor
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.models_invariants import InvariantMonitorRequest


@pytest.mark.parametrize("delta", ["0", "0.00001", "-0.00001"])
def test_order_conservation_within_tolerance(fixture_payload, delta):
    payload = deepcopy(fixture_payload["invariant_request"])
    payload["snapshot"]["open_quantity"] = str(Decimal("2") + Decimal(delta))
    assert run_invariant_monitor(InvariantMonitorRequest.model_validate_json(json.dumps(payload))).healthy


@pytest.mark.parametrize("delta", ["0.001", "-0.001", "1"])
def test_order_conservation_outside_tolerance(fixture_payload, delta):
    payload = deepcopy(fixture_payload["invariant_request"])
    payload["snapshot"]["open_quantity"] = str(Decimal("2") + Decimal(delta))
    assert not run_invariant_monitor(InvariantMonitorRequest.model_validate_json(json.dumps(payload))).healthy


@pytest.mark.parametrize("records", [[], ["x"], ["x", "y", "z"]])
def test_candidate_conservation(fixture_payload, records):
    payload = deepcopy(fixture_payload["invariant_request"])
    payload["snapshot"]["received_candidate_count"] = len(records)
    payload["snapshot"]["terminal_candidate_count"] = len(records)
    assert run_invariant_monitor(InvariantMonitorRequest.model_validate_json(json.dumps(payload))).healthy


def test_permuting_source_artifacts_preserves_runtime_decision(fixture_payload):
    base = deepcopy(fixture_payload)
    refs = [
        {"artifact_id":"a","content_sha256":"a"*64,"schema_version":"1","contract_version":"1"},
        {"artifact_id":"b","content_sha256":"b"*64,"schema_version":"1","contract_version":"1"},
    ]
    base["source_artifacts"] = refs
    reversed_payload = deepcopy(base)
    reversed_payload["source_artifacts"] = list(reversed(refs))
    a = run_runtime_assurance(RuntimeAssuranceRequest.model_validate_json(json.dumps(base)))
    b = run_runtime_assurance(RuntimeAssuranceRequest.model_validate_json(json.dumps(reversed_payload)))
    assert a.runtime_mode == b.runtime_mode
    assert a.evidence_bundle.shift_result == b.evidence_bundle.shift_result
