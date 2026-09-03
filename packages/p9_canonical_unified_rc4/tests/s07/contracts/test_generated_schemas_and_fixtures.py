from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s07_prospective_validation.runner import (
    ProspectiveMonitoringBundle,
    S7ExecutionRequest,
)

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[3]


def test_all_generated_json_schemas_are_valid() -> None:
    registry = json.loads((ROOT / "schemas" / "s07" / "SCHEMA_REGISTRY.json").read_text())
    assert len(registry["models"]) >= 50
    for item in registry["models"]:
        schema_path = Path(item["json_schema"])
        if schema_path.parts and schema_path.parts[0] == "schemas":
            schema_path = Path(*schema_path.parts[1:])
        schema = json.loads((ROOT / "schemas" / "s07" / schema_path).read_text())
        Draft202012Validator.check_schema(schema)


def test_valid_request_and_bundle_fixtures_parse() -> None:
    request = S7ExecutionRequest.model_validate_json(
        (ROOT / "fixtures" / "s07" / "valid" / "s7_execution_request.json").read_text()
    )
    bundle = ProspectiveMonitoringBundle.model_validate_json(
        (ROOT / "fixtures" / "s07" / "valid" / "prospective_monitoring_bundle.json").read_text()
    )
    assert request.header.run_id == bundle.payload.header.run_id
    bundle.verify_integrity()


def test_invalid_naive_datetime_fixture_is_rejected() -> None:
    with pytest.raises(ValidationError):
        S7ExecutionRequest.model_validate_json(
            (ROOT / "fixtures" / "s07" / "invalid" / "naive_datetime_request.json").read_text()
        )
