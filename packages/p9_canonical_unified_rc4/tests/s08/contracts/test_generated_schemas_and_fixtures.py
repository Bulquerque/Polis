from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s08_attribution.bundle import (
    ProspectiveAttributionBundle,
    S8ExecutionRequest,
)

ROOT = Path(__file__).parents[3]


def test_all_generated_json_schemas_are_draft_2020_12_valid() -> None:
    registry = json.loads(
        (ROOT / "schemas" / "s08" / "SCHEMA_REGISTRY.json").read_text(encoding="utf-8")
    )
    assert len(registry["models"]) == 50
    for item in registry["models"]:
        schema = json.loads((ROOT / "schemas" / "s08" / Path(*Path(item["json_schema"]).parts[1:])).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert (ROOT / "schemas" / "s08" / Path(*Path(item["yaml_schema"]).parts[1:])).is_file()


def test_valid_request_fixture_round_trips() -> None:
    raw = (ROOT / "fixtures" / "s08" / "valid" / "s8_execution_request.json").read_text()
    request = S8ExecutionRequest.model_validate_json(raw)
    assert request.header.run_id == "run-1"


def test_valid_bundle_fixture_round_trips_and_verifies_hash() -> None:
    raw = (
        ROOT
        / "fixtures"
        / "s08"
        / "valid"
        / "prospective_attribution_prospective_attribution_bundle.json"
    ).read_text()
    bundle = ProspectiveAttributionBundle.model_validate_json(raw)
    assert len(bundle.payload.module_receipts) == 8


@pytest.mark.parametrize(
    "fixture_name,model",
    [
        ("naive_datetime_request.json", S8ExecutionRequest),
        ("mixed_cycle_request.json", S8ExecutionRequest),
        ("tampered_bundle.json", ProspectiveAttributionBundle),
    ],
)
def test_invalid_fixtures_are_rejected(fixture_name: str, model: type) -> None:
    raw = (ROOT / "fixtures" / "s08" / "invalid" / fixture_name).read_text()
    with pytest.raises(ValidationError):
        model.model_validate_json(raw)
