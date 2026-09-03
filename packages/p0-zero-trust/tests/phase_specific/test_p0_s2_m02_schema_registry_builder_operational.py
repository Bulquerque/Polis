from copy import deepcopy
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules import (
    P0_S2_M02_schema_registry_builder as schema_registry_builder,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S2_M02_schema_registry_builder import (
    ContractValidationError,
    run_module,
)


AUTHORITY_ROOT = (
    WORKSPACE_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
)


def inventory_paths():
    return sorted(WORKSPACE_ROOT.glob("global_contracts_parallel_agents/**/*.schema.yaml")) + sorted(
        WORKSPACE_ROOT.glob("phase_*/**/*.schema.yaml")
    )


def valid_inputs():
    return {"schemas_all_phases": [str(path) for path in inventory_paths()]}


def mutate_schema(monkeypatch, target, mutation):
    target = target.resolve()
    original = schema_registry_builder._read_schema

    def reader(path):
        document, digest = original(path)
        if path == target:
            document = deepcopy(document)
            mutation(document)
        return document, digest

    monkeypatch.setattr(schema_registry_builder, "_read_schema", reader)


def test_builds_exact_real_inventory_and_accepts_governed_local_extensions():
    result = run_module(
        valid_inputs(),
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )
    registry = result["outputs"]["schema_registry"]

    authority_paths = sorted(AUTHORITY_ROOT.rglob("*.schema.yaml"))
    mirror_paths = sorted(WORKSPACE_ROOT.glob("phase_*/**/*.schema.yaml"))
    authority_by_name = {path.name: path for path in authority_paths}
    assert result["module_id"] == "P0.S2.M02"
    assert registry["inventory_count"] == registry["authority_schema_count"] + registry["mirror_count"]
    assert registry["authority_schema_count"] == len(registry["schemas"])
    assert registry["mirror_count"] == len(registry["mirrors"])
    assert registry["hashed_file_count"] == registry["inventory_count"]
    assert registry["mirror_divergence_count"] == 0
    assert registry["mirror_match_count"] + registry["mirror_divergence_count"] == registry["mirror_count"]
    assert registry["status"] == "PASS"
    assert registry["severity"] == "NONE"
    assert registry["release_blocking"] is False
    assert registry["schema_id_unique"] is True
    assert registry["artifact_name_unique"] is True
    assert registry["required_fields_not_empty"] is True
    assert registry["properties_types_consistent"] is True
    assert registry["inventory_complete"] is True
    assert registry["hashes_computed"] is True
    assert registry["mirror_authority_enforced"] is True
    assert all(len(entry["sha256"]) == 64 for entry in registry["schemas"])
    assert all(len(entry["sha256"]) == 64 for entry in registry["mirrors"])
    assert registry["findings"] == []
    assert {entry["content_relation"] for entry in registry["mirrors"]} == {
        "EXACT",
        "COMPATIBLE_EXTENSION",
    }


def test_blocks_local_extension_that_drops_authority_envelope(monkeypatch):
    candidates = sorted(WORKSPACE_ROOT.glob("phase_*/**/*.schema.yaml"))
    target = next(
        path
        for path in candidates
        if (AUTHORITY_ROOT / "schemas" / path.name).is_file()
        and yaml.safe_load((AUTHORITY_ROOT / "schemas" / path.name).read_text(encoding="utf-8")).get("required_fields")
    )
    authority = yaml.safe_load(
        (AUTHORITY_ROOT / "schemas" / target.name).read_text(encoding="utf-8")
    )
    required = authority["required_fields"][0]
    mutate_schema(
        monkeypatch,
        target,
        lambda document: document.__setitem__(
            "required_fields", [field for field in document["required_fields"] if field != required]
        ),
    )
    registry = run_module(valid_inputs(), {})["outputs"]["schema_registry"]
    assert registry["status"] == "FAIL"
    assert registry["release_blocking"] is True
    assert any(item["code"] == "MIRROR_POLICY_DIVERGENCE" for item in registry["findings"])


def test_blocks_local_extension_that_drops_authority_properties(monkeypatch):
    candidates = sorted(WORKSPACE_ROOT.glob("phase_*/**/*.schema.yaml"))
    target = next(
        path
        for path in candidates
        if (AUTHORITY_ROOT / "schemas" / path.name).is_file()
        and yaml.safe_load((AUTHORITY_ROOT / "schemas" / path.name).read_text(encoding="utf-8")).get("properties")
    )
    mutate_schema(monkeypatch, target, lambda document: document.pop("properties", None))
    registry = run_module(valid_inputs(), {})["outputs"]["schema_registry"]
    assert registry["release_blocking"] is True
    assert any("missing authority properties" in item["message"] for item in registry["findings"])


def test_registry_is_deterministic_except_for_created_at():
    first = run_module(valid_inputs(), {"created_at": "2026-07-19T00:00:00Z"})[
        "outputs"
    ]["schema_registry"]
    second = run_module(valid_inputs(), {"created_at": "2026-07-20T00:00:00Z"})[
        "outputs"
    ]["schema_registry"]
    assert first["artifact_id"] == second["artifact_id"]
    assert first["lineage_id"] == second["lineage_id"]
    assert first["created_at"] != second["created_at"]


def test_rejects_missing_or_duplicate_inventory_paths():
    paths = inventory_paths()
    with pytest.raises(ContractValidationError, match="does not match real inventory"):
        run_module({"schemas_all_phases": [str(path) for path in paths[:-1]]}, {})
    with pytest.raises(ContractValidationError, match="duplicate paths"):
        run_module({"schemas_all_phases": [str(path) for path in paths] + [str(paths[0])]}, {})


def test_rejects_path_outside_workspace(tmp_path):
    external = tmp_path / "external.schema.yaml"
    external.write_text("required_fields: [artifact_id]", encoding="utf-8")
    paths = inventory_paths()
    paths[0] = external
    with pytest.raises(ContractValidationError, match="escapes workspace"):
        run_module({"schemas_all_phases": [str(path) for path in paths]}, {})


def test_malformed_yaml_failure_is_propagated_from_real_inventory(monkeypatch):
    target = AUTHORITY_ROOT / "schemas" / "contract_registry.schema.yaml"
    original = schema_registry_builder._read_schema

    def reader(path):
        if path == target.resolve():
            raise ContractValidationError(f"invalid schema YAML at {path}")
        return original(path)

    monkeypatch.setattr(schema_registry_builder, "_read_schema", reader)
    with pytest.raises(ContractValidationError, match="invalid schema YAML"):
        run_module(valid_inputs(), {})


def test_rejects_duplicate_authoritative_schema_id(monkeypatch):
    target = AUTHORITY_ROOT / "schemas" / "contract_registry.schema.yaml"
    mutate_schema(
        monkeypatch,
        target,
        lambda document: document.__setitem__("schema_id", "schema_registry.v1"),
    )
    with pytest.raises(ContractValidationError, match="schema_id_unique"):
        run_module(valid_inputs(), {})


def test_rejects_empty_required_fields(monkeypatch):
    target = AUTHORITY_ROOT / "schemas" / "contract_registry.schema.yaml"
    mutate_schema(
        monkeypatch,
        target,
        lambda document: document.__setitem__("required_fields", []),
    )
    with pytest.raises(ContractValidationError, match="required_fields_not_empty"):
        run_module(valid_inputs(), {})


def test_rejects_incompatible_schema_version(monkeypatch):
    target = AUTHORITY_ROOT / "schemas" / "contract_registry.schema.yaml"
    mutate_schema(
        monkeypatch,
        target,
        lambda document: document.__setitem__("schema_version", "v15.0"),
    )
    with pytest.raises(ContractValidationError, match="schema version is incompatible"):
        run_module(valid_inputs(), {})


def test_rejects_inconsistent_properties_and_types(monkeypatch):
    target = AUTHORITY_ROOT / "schemas" / "contract_registry.schema.yaml"

    def mutation(document):
        document["properties"] = {
            field: {"type": "string"} for field in document["required_fields"]
        }
        document["properties"][document["required_fields"][0]]["type"] = "unknown_type"

    mutate_schema(monkeypatch, target, mutation)
    with pytest.raises(ContractValidationError, match="unsupported property type"):
        run_module(valid_inputs(), {})


def test_rejects_forbidden_fields_recursively_in_wrapper_and_schema(monkeypatch):
    inputs = {"schemas_all_phases": {"paths": [str(path) for path in inventory_paths()]}}
    inputs["schemas_all_phases"]["metadata"] = {"nested": [{"target": "leak"}]}
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(inputs, {})

    target = AUTHORITY_ROOT / "schemas" / "contract_registry.schema.yaml"
    mutate_schema(
        monkeypatch,
        target,
        lambda document: document.__setitem__("metadata", {"nested": {"rank_score": 1}}),
    )
    with pytest.raises(ContractValidationError, match="forbidden schema fields detected"):
        run_module(valid_inputs(), {})


def test_output_conforms_to_typed_registry_schema():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "schema_registry.schema.yaml").read_text(encoding="utf-8")
    )
    registry = run_module(
        valid_inputs(), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["schema_registry"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(registry) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    assert schema["properties"]["schemas"]["items"]["additionalProperties"] is False
    assert schema["properties"]["findings"]["items"]["properties"]["severity"]["const"] == "CRITICAL"


def test_blocks_nested_constraint_divergence_in_local_mirror(monkeypatch):
    target = ROOT / "schemas" / "io_compatibility_report.schema.yaml"

    def mutation(document):
        document["properties"]["compatibility_checks"]["items"]["properties"]["producer"]["type"] = "integer"

    mutate_schema(monkeypatch, target, mutation)
    registry = run_module(valid_inputs(), {})["outputs"]["schema_registry"]
    assert registry["status"] == "FAIL"
    finding = next(
        item for item in registry["findings"]
        if item["mirror_path"].endswith("io_compatibility_report.schema.yaml")
    )
    assert "compatibility_checks[].producer.type" in finding["message"]
