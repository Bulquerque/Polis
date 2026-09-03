from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.temporal_models import (
    TemporalPlanPolicy,
)


ROOT = Path(__file__).resolve().parents[1]


def test_all_generated_schemas_are_valid_draft_2020_12() -> None:
    registry = json.loads((ROOT / "registries" / "SCHEMA_REGISTRY.json").read_text())
    assert registry["schema_count"] == 52
    for record in registry["schemas"]:
        schema = json.loads((ROOT / record["schema_file"]).read_text())
        Draft202012Validator.check_schema(schema)


def test_positive_fixtures_validate_against_generated_schemas() -> None:
    registry = json.loads((ROOT / "registries" / "SCHEMA_REGISTRY.json").read_text())
    schema_by_name = {
        record["model"]: json.loads((ROOT / record["schema_file"]).read_text())
        for record in registry["schemas"]
    }
    for fixture in (ROOT / "fixtures" / "positive").glob("*.json"):
        Draft202012Validator(schema_by_name[fixture.stem]).validate(json.loads(fixture.read_text()))


def test_negative_temporal_fixture_is_rejected_by_python_contract() -> None:
    payload = json.loads(
        (ROOT / "fixtures" / "negative" / "TemporalPlanPolicy_naive_datetime.json").read_text()
    )
    with pytest.raises(ValidationError, match="timezone-aware"):
        TemporalPlanPolicy.model_validate_json(json.dumps(payload))
