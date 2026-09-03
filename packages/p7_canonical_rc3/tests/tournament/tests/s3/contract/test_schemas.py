from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = ROOT / "schemas"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_schema_is_valid_draft_2020_12():
    for path in sorted(SCHEMA_ROOT.glob("*.schema.yaml")):
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_input_fixture_validates_against_artifact_schemas():
    fixture = _load_json(ROOT / "fixtures/s3/minimal_input_fixture.json")
    for artifact_name, artifact in fixture.items():
        schema_path = SCHEMA_ROOT / f"{artifact_name}.schema.yaml"
        assert schema_path.is_file(), artifact_name
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(artifact)


def test_output_fixture_validates_against_artifact_schemas():
    fixture = _load_json(ROOT / "fixtures/s3/minimal_output_fixture.json")
    for artifact_name, artifact in fixture["outputs"].items():
        schema_path = SCHEMA_ROOT / f"{artifact_name}.schema.yaml"
        assert schema_path.is_file(), artifact_name
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(artifact)
