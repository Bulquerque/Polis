import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import S3Request


def test_public_model_rejects_unknown_field(s3_request):
    data = s3_request.model_dump(mode="json")
    data["unknown_economic_field"] = 1
    with pytest.raises(ValidationError):
        S3Request.model_validate(data)


def test_generated_schemas_are_valid():
    root = Path(__file__).resolve().parents[3] / "schemas/s3"
    schemas = list(root.glob("*.schema.json"))
    assert schemas
    for path in schemas:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema.get("additionalProperties") is False


def test_schema_rejects_unknown_top_level(s3_request):
    schema = json.loads((Path(__file__).resolve().parents[3]/"schemas/s3"/"S3Request.schema.json").read_text())
    data = s3_request.model_dump(mode="json")
    data["unexpected"] = True
    errors = list(Draft202012Validator(schema).iter_errors(data))
    assert errors


def _assert_closed(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is not True
        for value in node.values():
            _assert_closed(value)
    elif isinstance(node, list):
        for value in node:
            _assert_closed(value)


def test_all_nested_schema_objects_are_closed():
    root = Path(__file__).resolve().parents[3] / "schemas/s3"
    for path in root.glob("*.schema.json"):
        _assert_closed(json.loads(path.read_text(encoding="utf-8")))
