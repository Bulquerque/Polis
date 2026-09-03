from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from quant_pipeline.phase_08_contracts.p7 import P7RankingHandoffV1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.schema_export import export_schemas

from tests.agents.a1_s1.factories import full_fixture


def _walk_objects(schema: object):
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            yield schema
        for value in schema.values():
            yield from _walk_objects(value)
    elif isinstance(schema, list):
        for value in schema:
            yield from _walk_objects(value)


def test_exported_schemas_are_valid_draft_2020_12(tmp_path: Path) -> None:
    paths = export_schemas(tmp_path)
    assert len(paths) == 15
    for path in paths:
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_object_schemas_are_closed_when_properties_are_declared(tmp_path: Path) -> None:
    for path in export_schemas(tmp_path):
        schema = json.loads(path.read_text())
        for object_schema in _walk_objects(schema):
            assert object_schema.get("additionalProperties") is False, (path.name, object_schema)


def test_p7_fixture_validates_against_generated_schema(tmp_path: Path) -> None:
    fixture = full_fixture(ranked=True)
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "P7_TO_P8_RANKING_HANDOFF_V1.schema.json").read_text())
    instance = json.loads(fixture.request.p7_handoff_bytes)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, [error.message for error in errors]


def test_schema_rejects_unknown_root_field(tmp_path: Path) -> None:
    fixture = full_fixture(ranked=True)
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "P7_TO_P8_RANKING_HANDOFF_V1.schema.json").read_text())
    instance = json.loads(fixture.request.p7_handoff_bytes)
    instance["unknown"] = 1
    errors = list(Draft202012Validator(schema).iter_errors(instance))
    assert errors
