from copy import deepcopy
from pathlib import Path
import hashlib
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M01_phase_registry_loader import (
    run_module as run_phase_registry_loader,
)
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M02_subphase_registry_loader import (
    ContractValidationError,
    run_module,
)


PHASE_REGISTRY = ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"
SUBPHASE_REGISTRY = ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml"
GLOBAL_SUBPHASE_REGISTRY = (
    WORKSPACE_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
    / "source_of_truth"
    / "registries"
    / "subphase_registry.yaml"
)
VALID_ARCHITECTURE = {
    "authority": "global_master",
    "pipeline_version": "V14.1-RC4.1",
    "phase_registry_id": "phase_registry_v14_1_rc4_1",
}


def validated_phase_registry():
    return run_phase_registry_loader(
        {
            "phase_registry_yaml": str(PHASE_REGISTRY),
            "global_architecture_config": VALID_ARCHITECTURE,
        },
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["validated_phase_registry"]


def canonical_subphase_registry():
    return yaml.safe_load(SUBPHASE_REGISTRY.read_text(encoding="utf-8"))


def test_canonical_registry_and_p0_mirror_are_byte_identical():
    assert SUBPHASE_REGISTRY.read_bytes() == GLOBAL_SUBPHASE_REGISTRY.read_bytes()


def test_loads_all_canonical_subphases_and_preserves_parent_connection_and_provenance():
    parent = validated_phase_registry()
    result = run_module(
        {
            "validated_phase_registry": parent,
            "subphase_registry_yaml": str(SUBPHASE_REGISTRY),
        },
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )
    artifact = result["outputs"]["validated_subphase_registry"]

    assert result["module_id"] == "P0.S1.M02"
    assert artifact["phase_registry_lineage_id"] == parent["lineage_id"]
    assert artifact["phase_count"] == 10
    assert artifact["subphase_count"] == len(canonical_subphase_registry()["subphases"])
    assert artifact["subphases"][0] == {"subphase_id": "P0.S1", "phase_id": "P0"}
    assert artifact["subphases"][-1] == {"subphase_id": "P9.S5", "phase_id": "P9"}
    assert artifact["subphase_id_unique"] is True
    assert artifact["subphase_belongs_to_existing_phase"] is True
    assert artifact["exact_subphase_set"] is True
    assert artifact["provenance_valid"] is True
    assert artifact["registry_version_compatible"] is True
    assert artifact["promotion_blocked"] is True

    sources = artifact["provenance"]["derived_from"]
    assert {source["phase_id"] for source in sources} == {f"P{i}" for i in range(10)}
    for source in sources:
        path = WORKSPACE_ROOT / source["source_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_rejects_duplicate_subphase_ids_before_exact_coverage_check():
    registry = canonical_subphase_registry()
    registry["subphases"][1]["subphase_id"] = registry["subphases"][0]["subphase_id"]
    with pytest.raises(ContractValidationError, match="subphase_id_unique"):
        run_module(
            {"validated_phase_registry": validated_phase_registry(), "subphase_registry_yaml": registry},
            {},
        )


def test_rejects_subphase_whose_declared_parent_does_not_exist():
    registry = canonical_subphase_registry()
    registry["subphases"][0]["phase_id"] = "P10"
    with pytest.raises(ContractValidationError, match="subphase_belongs_to_existing_phase"):
        run_module(
            {"validated_phase_registry": validated_phase_registry(), "subphase_registry_yaml": registry},
            {},
        )


def test_rejects_incomplete_subphase_set():
    registry = canonical_subphase_registry()
    registry["subphases"].pop()
    with pytest.raises(ContractValidationError, match="exact_subphase_set"):
        run_module(
            {"validated_phase_registry": validated_phase_registry(), "subphase_registry_yaml": registry},
            {},
        )


def test_rejects_invalid_yaml_with_contract_error(tmp_path):
    path = tmp_path / "invalid-subphases.yaml"
    path.write_text("subphases: [not-closed", encoding="utf-8")
    with pytest.raises(ContractValidationError, match="invalid YAML for subphase registry"):
        run_module(
            {
                "validated_phase_registry": validated_phase_registry(),
                "subphase_registry_yaml": path,
            },
            {},
        )


@pytest.mark.parametrize(
    "parent_mutation,expected",
    [
        (lambda parent: parent.pop("lineage_id"), "missing fields"),
        (lambda parent: parent.__setitem__("pipeline_version", "V15.0"), "pipeline version"),
        (lambda parent: parent.__setitem__("phase_count", 9), "exactly P0-P9"),
    ],
)
def test_rejects_invalid_validated_phase_registry(parent_mutation, expected):
    parent = validated_phase_registry()
    parent_mutation(parent)
    with pytest.raises(ContractValidationError, match=expected):
        run_module(
            {"validated_phase_registry": parent, "subphase_registry_yaml": str(SUBPHASE_REGISTRY)},
            {},
        )


def test_rejects_incompatible_registry_and_runtime_versions():
    registry = canonical_subphase_registry()
    registry["schema_version"] = "v15.0"
    with pytest.raises(ContractValidationError, match="schema version is incompatible"):
        run_module(
            {"validated_phase_registry": validated_phase_registry(), "subphase_registry_yaml": registry},
            {},
        )
    with pytest.raises(ContractValidationError, match="pipeline version is incompatible"):
        run_module(
            {
                "validated_phase_registry": validated_phase_registry(),
                "subphase_registry_yaml": str(SUBPHASE_REGISTRY),
            },
            {"pipeline_version": "V15.0"},
        )


def test_rejects_tampered_provenance_hash():
    registry = canonical_subphase_registry()
    registry["provenance"]["derived_from"][0]["sha256"] = "0" * 64
    with pytest.raises(ContractValidationError, match="provenance hash mismatch"):
        run_module(
            {"validated_phase_registry": validated_phase_registry(), "subphase_registry_yaml": registry},
            {},
        )


@pytest.mark.parametrize("container", ["validated_phase_registry", "subphase_registry_yaml"])
def test_rejects_forbidden_fields_recursively(container):
    inputs = {
        "validated_phase_registry": validated_phase_registry(),
        "subphase_registry_yaml": canonical_subphase_registry(),
    }
    if container == "validated_phase_registry":
        inputs[container]["phases"][0]["metadata"] = {"rank_score": 1}
    else:
        inputs[container]["provenance"]["metadata"] = [{"trade_decision": "BUY"}]
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(inputs, {})


def test_rejects_symbolic_placeholders_and_non_mapping_config():
    with pytest.raises(ContractValidationError, match="materialized artifact"):
        run_module(
            {
                "validated_phase_registry": {"source": "validated_phase_registry"},
                "subphase_registry_yaml": str(SUBPHASE_REGISTRY),
            },
            {},
        )


def test_rejects_forged_parent_content_and_lineage():
    parent = deepcopy(validated_phase_registry())
    parent["phases"][0]["package_name"] = "evil-package"
    parent["lineage_id"] = "sha256:" + "f" * 64
    with pytest.raises(ContractValidationError, match="canonical packages and planes"):
        run_module(
            {
                "validated_phase_registry": parent,
                "subphase_registry_yaml": str(SUBPHASE_REGISTRY),
            },
            {},
        )

    parent = deepcopy(validated_phase_registry())
    parent["lineage_id"] = "sha256:" + "f" * 64
    with pytest.raises(ContractValidationError, match="lineage_id does not match content"):
        run_module(
            {
                "validated_phase_registry": parent,
                "subphase_registry_yaml": str(SUBPHASE_REGISTRY),
            },
            {},
        )
    with pytest.raises(ContractValidationError, match="config must be a dict"):
        run_module(
            {
                "validated_phase_registry": validated_phase_registry(),
                "subphase_registry_yaml": str(SUBPHASE_REGISTRY),
            },
            [],
        )


def test_output_conforms_to_enriched_schema_contract():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "validated_subphase_registry.schema.yaml").read_text(
            encoding="utf-8"
        )
    )
    artifact = run_module(
        {
            "validated_phase_registry": validated_phase_registry(),
            "subphase_registry_yaml": str(SUBPHASE_REGISTRY),
        },
        {"created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["validated_subphase_registry"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(artifact) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    assert schema["properties"]["subphase_count"]["const"] == len(canonical_subphase_registry()["subphases"])
