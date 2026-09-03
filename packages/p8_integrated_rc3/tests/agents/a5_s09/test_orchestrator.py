import json
from copy import deepcopy

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import RuntimeAssuranceRequest, RuntimeMode, run_runtime_assurance


def test_normal_end_to_end(normal_request):
    result = run_runtime_assurance(normal_request)
    assert result.runtime_mode is RuntimeMode.NORMAL
    assert result.evidence_bundle.production_promotion_allowed is False
    assert result.evidence_bundle.bundle_id.startswith("reb_")


def test_replay_is_deterministic(normal_request):
    first = run_runtime_assurance(normal_request)
    second = run_runtime_assurance(normal_request)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_material_shift_end_to_end(fixture_payload):
    payload = deepcopy(fixture_payload)
    payload["shift_request"]["observations"][0]["value"] = 10.0
    request = RuntimeAssuranceRequest.model_validate_json(json.dumps(payload))
    assert run_runtime_assurance(request).runtime_mode is RuntimeMode.HOLD_NO_NEW_RISK


def test_no_shadow_is_valid(normal_request):
    assert run_runtime_assurance(normal_request).evidence_bundle.shadow_result is None
