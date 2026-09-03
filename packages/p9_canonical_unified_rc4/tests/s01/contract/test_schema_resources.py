from __future__ import annotations

import pytest

from quant_pipeline.phase_09.contracts.schema_resources import list_schema_names, read_schema


def test_generated_schema_resources_are_available() -> None:
    names = list_schema_names()
    assert "handoff.P8EvaluationHandoffV1.schema.json" in names
    assert len(names) == 74
    schema = read_schema("handoff.P8EvaluationHandoffV1.schema.json")
    assert schema["title"] == "P8EvaluationHandoffV1"


def test_schema_resource_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        read_schema("../secret.json")
    with pytest.raises(FileNotFoundError):
        read_schema("missing.schema.json")
