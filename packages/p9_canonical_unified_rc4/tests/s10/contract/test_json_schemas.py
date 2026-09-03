from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]


def test_all_json_schemas_are_valid_draft_2020_12() -> None:
    schemas = tuple((ROOT / "schemas" / "s10").glob("*.schema.json"))
    assert len(schemas) == 19
    for path in schemas:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(schema)


def test_generated_fixtures_validate_against_public_schemas() -> None:
    pairs = (
        (
            "s10_input_bundle.schema.json",
            "fixtures/s10/input/p9_s10_input_bundle_sample.json",
        ),
        (
            "s10_subphase_delivery.schema.json",
            "fixtures/s10/output/p9_s10_subphase_delivery_sample.json",
        ),
        (
            "s10_execution_envelope.schema.json",
            "fixtures/s10/output/p9_s10_execution_envelope_sample.json",
        ),
        (
            "p9_release_publication_manifest.schema.json",
            "fixtures/s10/output/p9_release_publication_manifest_sample.json",
        ),
    )
    for schema_name, fixture_name in pairs:
        schema = json.loads((ROOT / "schemas" / "s10" / schema_name).read_text(encoding="utf-8"))
        fixture = json.loads((ROOT / fixture_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(fixture)
