from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M01_phase_registry_loader import (
    ContractValidationError,
    run_module,
)


CANONICAL_REGISTRY = ROOT / "source_of_truth" / "registries" / "phase_registry.yaml"
VALID_ARCHITECTURE = {
    "authority": "global_master",
    "pipeline_version": "V14.1-RC4.1",
    "phase_registry_id": "phase_registry_v14_1_rc4_1",
}


def test_loads_canonical_registry_and_preserves_governance_semantics():
    result = run_module(
        {
            "phase_registry_yaml": str(CANONICAL_REGISTRY),
            "global_architecture_config": VALID_ARCHITECTURE,
        },
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )
    artifact = result["outputs"]["validated_phase_registry"]

    assert result["module_id"] == "P0.S1.M01"
    assert artifact["phase_count"] == 10
    assert [item["phase_id"] for item in artifact["phases"]] == [f"P{i}" for i in range(10)]
    assert artifact["phases"][0]["plane"] == "zero_trust_control"
    assert artifact["phase_id_unique"] is True
    assert artifact["phase_type_declared"] is True
    assert artifact["registry_id_declared"] is True
    assert artifact["package_name_declared"] is True
    assert artifact["global_architecture_config_valid"] is True
    assert artifact["registry_version_compatible"] is True
    assert artifact["architecture_authority"] == "global_master"
    assert all(item["package_name"] for item in artifact["phases"])
    assert artifact["lineage_id"].startswith("sha256:")
    assert artifact["validation_evidence_status"] == "domain_oracle_pass_pending_independent_judge"
    assert artifact["promotion_blocked"] is True


def test_rejects_duplicate_phase_ids():
    registry = {
        "registry_id": "duplicate",
        "phases": [
            {"phase_id": "P0", "package_name": "a", "plane": "zero_trust_control"},
            {"phase_id": "P0", "package_name": "b", "plane": "economic_pipeline"},
        ],
    }
    with pytest.raises(ContractValidationError, match="phase_id_unique"):
        run_module(
            {"phase_registry_yaml": registry, "global_architecture_config": VALID_ARCHITECTURE},
            {},
        )


def test_rejects_phase_without_declared_plane():
    registry = {
        "registry_id": "missing-plane",
        "phases": [{"phase_id": "P0", "package_name": "a"}],
    }
    with pytest.raises(ContractValidationError, match="phase_type_declared"):
        run_module(
            {"phase_registry_yaml": registry, "global_architecture_config": VALID_ARCHITECTURE},
            {},
        )


def test_rejects_missing_registry_id():
    registry = {
        "phases": [
            {
                "phase_id": "P0",
                "package_name": "phase_00_zero_trust_guardian_agent_package_RC4_1",
                "plane": "zero_trust_control",
            }
        ]
    }
    with pytest.raises(ContractValidationError, match="registry_id_declared"):
        run_module(
            {"phase_registry_yaml": registry, "global_architecture_config": VALID_ARCHITECTURE},
            {},
        )


def test_rejects_missing_package_name():
    registry = {
        "registry_id": "phase_registry_v14_1_rc4_1",
        "phases": [{"phase_id": "P0", "plane": "zero_trust_control"}],
    }
    with pytest.raises(ContractValidationError, match="package_name_declared"):
        run_module(
            {"phase_registry_yaml": registry, "global_architecture_config": VALID_ARCHITECTURE},
            {},
        )


def test_rejects_invalid_yaml_with_contract_error(tmp_path):
    invalid_yaml = tmp_path / "invalid-registry.yaml"
    invalid_yaml.write_text("phases: [not-closed", encoding="utf-8")
    with pytest.raises(ContractValidationError, match="invalid YAML for phase registry"):
        run_module(
            {
                "phase_registry_yaml": invalid_yaml,
                "global_architecture_config": VALID_ARCHITECTURE,
            },
            {},
        )


@pytest.mark.parametrize(
    "architecture",
    [
        {},
        {"source": "global_architecture_config"},
        {"authority": "untrusted_local"},
        {"authority": "global_master", "pipeline_version": "V15.0"},
        {
            "authority": "global_master",
            "phase_registry_id": "phase_registry_v13",
        },
    ],
)
def test_rejects_invalid_global_architecture_config(architecture):
    with pytest.raises(ContractValidationError, match="global_architecture_config"):
        run_module(
            {
                "phase_registry_yaml": str(CANONICAL_REGISTRY),
                "global_architecture_config": architecture,
            },
            {},
        )


def test_rejects_incompatible_runtime_and_registry_versions():
    with pytest.raises(ContractValidationError, match="pipeline version is incompatible"):
        run_module(
            {
                "phase_registry_yaml": str(CANONICAL_REGISTRY),
                "global_architecture_config": VALID_ARCHITECTURE,
            },
            {"pipeline_version": "V15.0"},
        )

    registry = yaml.safe_load(CANONICAL_REGISTRY.read_text(encoding="utf-8"))
    registry["registry_id"] = "phase_registry_v15_0"
    with pytest.raises(ContractValidationError, match="registry version is incompatible"):
        run_module(
            {"phase_registry_yaml": registry, "global_architecture_config": VALID_ARCHITECTURE},
            {},
        )


@pytest.mark.parametrize("container", ["phase_registry_yaml", "global_architecture_config"])
def test_rejects_forbidden_fields_recursively(container):
    inputs = {
        "phase_registry_yaml": str(CANONICAL_REGISTRY),
        "global_architecture_config": VALID_ARCHITECTURE,
    }
    if container == "phase_registry_yaml":
        registry = yaml.safe_load(CANONICAL_REGISTRY.read_text(encoding="utf-8"))
        registry["phases"][0]["metadata"] = {"future_return": 0.5}
        inputs[container] = registry
    else:
        inputs[container] = {
            **VALID_ARCHITECTURE,
            "nested": [{"policy": {"trade_decision": "BUY"}}],
        }
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(inputs, {})


def test_output_conforms_to_enriched_schema_contract():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "validated_phase_registry.schema.yaml").read_text(encoding="utf-8")
    )
    artifact = run_module(
        {
            "phase_registry_yaml": str(CANONICAL_REGISTRY),
            "global_architecture_config": VALID_ARCHITECTURE,
        },
        {"created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["validated_phase_registry"]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(artifact) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    assert schema["properties"]["phases"]["items"]["additionalProperties"] is False


def test_rejects_symbolic_placeholder_as_positive_input():
    with pytest.raises(ContractValidationError, match="registry mapping or an explicit YAML path"):
        run_module(
            {
                "phase_registry_yaml": {"source": "phase_registry_yaml"},
                "global_architecture_config": {"source": "global_architecture_config"},
            },
            {},
        )


def test_rejects_non_mapping_config_instead_of_coercing_it():
    with pytest.raises(ContractValidationError, match="config must be a dict"):
        run_module(
            {
                "phase_registry_yaml": str(CANONICAL_REGISTRY),
                "global_architecture_config": VALID_ARCHITECTURE,
            },
            [],
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda registry: registry.update(phases=registry["phases"][:1]),
        lambda registry: registry["phases"][1].update(
            package_name="evil_phase_01_package"
        ),
        lambda registry: registry["phases"][0].update(plane="economic_pipeline"),
        lambda registry: registry["phases"].reverse(),
        lambda registry: registry.update(untrusted_override=True),
        lambda registry: registry["phases"][0].update(untrusted_override=True),
    ],
)
def test_rejects_partial_or_mutated_inline_registry(mutation):
    registry = yaml.safe_load(CANONICAL_REGISTRY.read_text(encoding="utf-8"))
    mutation(registry)

    with pytest.raises(ContractValidationError, match="canonical P0-P9"):
        run_module(
            {
                "phase_registry_yaml": registry,
                "global_architecture_config": VALID_ARCHITECTURE,
            },
            {},
        )


@pytest.mark.parametrize(
    "architecture",
    [
        {
            "authority": "global_contracts_parallel_agents/evil/source_of_truth",
            "pipeline_version": "V14.1-RC4.1",
            "phase_registry_id": "phase_registry_v14_1_rc4_1",
        },
        {
            "authority": "global_master",
            "phase_registry_id": "phase_registry_v14_1_rc4_1",
        },
        {
            "authority": "global_master",
            "pipeline_version": "V14.1-RC4.1",
        },
    ],
)
def test_rejects_unbound_or_lookalike_architecture_identity(architecture):
    with pytest.raises(ContractValidationError, match="global_architecture_config"):
        run_module(
            {
                "phase_registry_yaml": str(CANONICAL_REGISTRY),
                "global_architecture_config": architecture,
            },
            {},
        )


def test_accepts_exact_registry_and_architecture_from_explicit_paths(tmp_path):
    architecture_path = tmp_path / "architecture.yaml"
    architecture_path.write_text(yaml.safe_dump(VALID_ARCHITECTURE), encoding="utf-8")

    artifact = run_module(
        {
            "phase_registry_yaml": {"path": str(CANONICAL_REGISTRY)},
            "global_architecture_config": {"path": str(architecture_path)},
        },
        {},
    )["outputs"]["validated_phase_registry"]

    assert artifact["phase_count"] == 10
    assert artifact["architecture_authority"] == "global_master"
