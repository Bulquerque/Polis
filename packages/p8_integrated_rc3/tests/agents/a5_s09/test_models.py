import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import RuntimeAssuranceRequest


@pytest.mark.parametrize("path,value", [
    (("context","decision_time"), "2026-08-03T18:00:00"),
    (("context","observed_at"), "2026-08-03T17:59:00Z"),
    (("shift_request","policy","alpha"), 0.0),
    (("shift_request","policy","minimum_observations"), 0),
    (("invariant_request","snapshot","margin_limit"), "0"),
    (("invariant_request","snapshot","maximum_loss_limit"), "0"),
])
def test_invalid_contract_fields(fixture_payload, path, value):
    payload = deepcopy(fixture_payload)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        RuntimeAssuranceRequest.model_validate_json(json.dumps(payload))


def test_extra_field_forbidden(fixture_payload):
    payload = deepcopy(fixture_payload)
    payload["unexpected"] = 1
    with pytest.raises(ValidationError):
        RuntimeAssuranceRequest.model_validate_json(json.dumps(payload))


def test_models_are_frozen(normal_request):
    with pytest.raises(ValidationError):
        normal_request.context.run_id = "other"


def test_contexts_must_match(fixture_payload):
    payload = deepcopy(fixture_payload)
    payload["shift_request"]["context"]["run_id"] = "different"
    with pytest.raises(ValidationError):
        RuntimeAssuranceRequest.model_validate_json(json.dumps(payload))
