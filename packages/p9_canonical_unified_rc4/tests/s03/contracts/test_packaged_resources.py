from __future__ import annotations

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.resource_access import (
    read_json_resource,
)


def test_schema_and_registry_are_available_as_package_resources() -> None:
    schema = read_json_resource("schemas", "TemporalPlanPolicy.schema.json")
    registry = read_json_resource("registries", "MODULE_REGISTRY.json")
    assert schema["title"] == "TemporalPlanPolicy"
    assert registry["module_count"] == 7


def test_resource_accessor_blocks_path_traversal() -> None:
    with pytest.raises(ValueError, match="invalid"):
        read_json_resource("schemas", "../secret.json")
    with pytest.raises(ValueError, match="category"):
        read_json_resource("other", "MODULE_REGISTRY.json")
