from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3] / "schemas/s4"


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def test_generated_schemas_are_valid_and_structured_objects_are_closed():
    paths = sorted(ROOT.glob("*.schema.json"))
    assert len(paths) >= 10
    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        for node in _walk(schema):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, (path.name, node)


def test_request_schema_forbids_unknown_top_level_fields():
    schema = json.loads((ROOT / "S4Request.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
