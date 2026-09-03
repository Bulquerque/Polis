
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.schema_export import export_schemas
from tests.agents.a1_s2.factories import build_input


def test_exported_schemas_are_valid_and_strict(tmp_path: Path):
    paths=export_schemas(tmp_path)
    assert len(paths)==9
    for path in paths:
        schema=json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"]=="https://json-schema.org/draft/2020-12/schema"
        assert schema.get("additionalProperties") is False


def test_input_schema_rejects_extra_property(tmp_path: Path):
    path=export_schemas(tmp_path)[0]
    schema=json.loads(path.read_text())
    bundle,_=build_input()
    payload=bundle.model_dump(mode="json")
    payload["surprise"]=1
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(payload)
