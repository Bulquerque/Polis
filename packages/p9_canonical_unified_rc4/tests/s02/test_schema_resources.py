from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.schema_resources import (
    list_schema_names,
    read_schema,
)


def test_packaged_schemas_are_discoverable_and_valid() -> None:
    names = list_schema_names()
    assert "schema-index.json" in names
    assert len(names) > 40
    index = read_schema("schema-index.json")
    assert index["model_count"] == len(names) - 1
    for name in names:
        schema = read_schema(name)
        if name.endswith(".schema.json"):
            Draft202012Validator.check_schema(schema)


def test_schema_resource_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        read_schema("../schema-index.json")
