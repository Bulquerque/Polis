from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M04_connection_matrix_validator import (
    ContractValidationError,
    _validate_artifact,
    run_module,
)


LINEAGE_A = "sha256:" + "a" * 64
LINEAGE_B = "sha256:" + "b" * 64
CANONICAL_MATRIX = ROOT / "contracts" / "MODULE_IO_MATRIX.yaml"

MODULES = [
    ("P0.S1.M01", "phase_registry_loader"),
    ("P0.S1.M02", "subphase_registry_loader"),
    ("P0.S1.M03", "module_registry_loader"),
    ("P0.S1.M04", "connection_matrix_validator"),
    ("P0.S1.M05", "forbidden_connection_detector"),
]


def _registered_module(module_id: str, module_name: str) -> dict:
    selector = module_id.replace(".", "_")
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase_id": "P0",
        "subphase_id": "P0.S1",
        "contract_path": (
            "phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1/"
            f"modules/{selector}_{module_name}.yaml"
        ),
        "contract_sha256": "c" * 64,
    }


def _row(
    module_id: str,
    module_name: str,
    *,
    dependencies: list[str],
    consumed: list[str],
    phase_inputs: list[str],
    targets: list[str],
    emitted: list[str],
    phase_outputs: list[str] | None = None,
) -> dict:
    return {
        "module_id": module_id,
        "module_name": module_name,
        "subphase": "P0.S1",
        "consumes_from": {
            "modules": dependencies,
            "artifacts": consumed,
            "phase_inputs": phase_inputs,
        },
        "emits_to": {
            "modules": targets,
            "artifacts": emitted,
            "phase_outputs": phase_outputs or [],
        },
        "module_contract": f"modules/{module_id.replace('.', '_')}_{module_name}.yaml",
    }


def forged_partial_inputs() -> dict:
    phase_registry = {
        "registry_id": "phase_registry_v14_1_rc4_1",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": LINEAGE_A,
        "phase_count": 1,
        "phases": [
            {
                "phase_id": "P0",
                "package_name": "phase_00_zero_trust_guardian_agent_package_RC4_1",
                "plane": "zero_trust_control",
            }
        ],
        "promotion_blocked": True,
    }
    module_registry = {
        "registry_id": "module_registry_v14_1_rc4_1",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": LINEAGE_B,
        "module_count": len(MODULES),
        "modules": [_registered_module(*module) for module in MODULES],
        "promotion_blocked": True,
    }
    matrix = {
        "phase": "P0",
        "rc": "RC4.1",
        "contract": "MODULE_IO_MATRIX",
        "format": "compact_contract_v4",
        "module_io_matrix": [
            _row(
                "P0.S1.M01",
                "phase_registry_loader",
                dependencies=[],
                consumed=["phase_registry_yaml", "global_architecture_config"],
                phase_inputs=["phase_registry_yaml", "global_architecture_config"],
                targets=["P0.S1.M02", "P0.S1.M03", "P0.S1.M04"],
                emitted=["validated_phase_registry"],
            ),
            _row(
                "P0.S1.M02",
                "subphase_registry_loader",
                dependencies=["P0.S1.M01"],
                consumed=["validated_phase_registry", "subphase_registry_yaml"],
                phase_inputs=["subphase_registry_yaml"],
                targets=["P0.S1.M03"],
                emitted=["validated_subphase_registry"],
            ),
            _row(
                "P0.S1.M03",
                "module_registry_loader",
                dependencies=["P0.S1.M01", "P0.S1.M02"],
                consumed=[
                    "validated_phase_registry",
                    "validated_subphase_registry",
                    "module_registry_yaml",
                ],
                phase_inputs=["module_registry_yaml"],
                targets=["P0.S1.M04"],
                emitted=["validated_module_registry"],
            ),
            _row(
                "P0.S1.M04",
                "connection_matrix_validator",
                dependencies=["P0.S1.M01", "P0.S1.M03"],
                consumed=[
                    "connection_matrix_yaml",
                    "validated_phase_registry",
                    "validated_module_registry",
                ],
                phase_inputs=["connection_matrix_yaml"],
                targets=["P0.S1.M05"],
                emitted=["validated_connection_matrix"],
            ),
            _row(
                "P0.S1.M05",
                "forbidden_connection_detector",
                dependencies=["P0.S1.M04"],
                consumed=[
                    "validated_connection_matrix",
                    "forbidden_connection_matrix_yaml",
                    "module_io_matrix_all_phases",
                ],
                phase_inputs=[
                    "forbidden_connection_matrix_yaml",
                    "module_io_matrix_all_phases",
                ],
                targets=[],
                emitted=["forbidden_connection_report"],
                phase_outputs=["forbidden_connection_report"],
            ),
        ],
    }
    return {
        "connection_matrix_yaml": matrix,
        "validated_phase_registry": phase_registry,
        "validated_module_registry": module_registry,
    }


def _canonical_materialized_inputs() -> dict:
    phases = yaml.safe_load(
        (ROOT / "source_of_truth" / "registries" / "phase_registry.yaml").read_text(
            encoding="utf-8"
        )
    )
    modules = yaml.safe_load(
        (ROOT / "source_of_truth" / "registries" / "module_registry.yaml").read_text(
            encoding="utf-8"
        )
    )
    phase_normalized = {
        "registry_id": phases["registry_id"],
        "architecture_binding": {
            "authority": "GLOBAL_ARCHITECTURE_CONFIG",
            "pipeline_version": "V14.1-RC4.1",
            "phase_registry_id": phases["registry_id"],
        },
        "phases": phases["phases"],
    }
    phase_digest = hashlib.sha256(
        json.dumps(phase_normalized, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    module_digest = hashlib.sha256(
        json.dumps(modules["modules"], sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    validated_phases = {
        "artifact_id": f"validated-phase-registry-{phase_digest[:12]}",
        "created_at": "2026-07-19T00:00:00Z",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": f"sha256:{phase_digest}",
        "source_path": "source_of_truth/registries/phase_registry.yaml",
        "architecture_source_path": "global_architecture_config.yaml",
        "registry_id": phases["registry_id"],
        "architecture_authority": "GLOBAL_ARCHITECTURE_CONFIG",
        "phase_count": len(phases["phases"]),
        "phases": phases["phases"],
        "phase_id_unique": True,
        "phase_type_declared": True,
        "registry_id_declared": True,
        "package_name_declared": True,
        "global_architecture_config_valid": True,
        "registry_version_compatible": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    validated_modules = {
        "artifact_id": f"validated-module-registry-{module_digest[:12]}",
        "created_at": "2026-07-19T00:00:00Z",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": f"sha256:{module_digest}",
        "source_path": "source_of_truth/registries/module_registry.yaml",
        "registry_id": modules["registry_id"],
        "module_count": len(modules["modules"]),
        "modules": modules["modules"],
        "module_id_unique": True,
        "module_has_contract": True,
        "module_parent_valid": True,
        "contract_identity_valid": True,
        "contract_hash_valid": True,
        "registry_version_compatible": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    return {
        "connection_matrix_yaml": str(CANONICAL_MATRIX),
        "validated_phase_registry": validated_phases,
        "validated_module_registry": validated_modules,
    }


def valid_inputs() -> dict:
    inputs = _canonical_materialized_inputs()
    inputs["connection_matrix_yaml"] = yaml.safe_load(CANONICAL_MATRIX.read_text(encoding="utf-8"))
    return inputs


def test_validates_real_inline_connection_matrix_and_emits_traceable_artifact():
    inputs = valid_inputs()
    result = run_module(
        inputs,
        {"created_at": "2026-07-19T00:00:00Z", "pipeline_version": "V14.1-RC4.1"},
    )
    artifact = result["outputs"]["validated_connection_matrix"]

    assert result["module_id"] == "P0.S1.M04"
    assert artifact["module_count"] == 40
    assert artifact["connection_count"] > 40
    assert len(artifact["connections"]) == artifact["connection_count"]
    assert artifact["phase_registry_lineage_id"] == inputs_lineage(inputs, "validated_phase_registry")
    assert artifact["module_registry_lineage_id"] == inputs_lineage(inputs, "validated_module_registry")
    assert artifact["registry_identity_valid"] is True
    assert artifact["dependency_reciprocity_valid"] is True
    assert artifact["artifact_flow_valid"] is True
    assert artifact["economic_connections_allowed_only"] is True
    assert artifact["zero_trust_plane_metadata_only"] is True
    assert artifact["promotion_blocked"] is True
    assert artifact["validation_evidence_status"] == "domain_oracle_pass_pending_independent_judge"


def test_validates_the_canonical_40_module_p0_matrix_against_real_registries():
    artifact = run_module(
        _canonical_materialized_inputs(), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["validated_connection_matrix"]

    assert artifact["source_path"] == CANONICAL_MATRIX.resolve().as_posix()
    assert artifact["module_count"] == 40
    assert artifact["connection_count"] > 40
    assert {row["module_id"] for row in artifact["module_io_matrix"]} == {
        f"P0.S{subphase}.M{module:02d}"
        for subphase, count in ((1, 5), (2, 5), (3, 4), (4, 5), (5, 6), (6, 4), (7, 4), (8, 3), (9, 4))
        for module in range(1, count + 1)
    }


def test_lineage_is_deterministic_and_binds_both_upstream_registries():
    inputs = valid_inputs()
    first = run_module(inputs, {"created_at": "2026-07-19T00:00:00Z"})["outputs"][
        "validated_connection_matrix"
    ]
    second = run_module(inputs, {"created_at": "2026-07-20T00:00:00Z"})["outputs"][
        "validated_connection_matrix"
    ]
    assert first["lineage_id"] == second["lineage_id"]
    changed = deepcopy(inputs)
    changed["validated_module_registry"]["lineage_id"] = "sha256:" + "d" * 64
    with pytest.raises(ContractValidationError, match="lineage_id does not bind"):
        run_module(changed, {"created_at": "2026-07-19T00:00:00Z"})


def inputs_lineage(inputs: dict, registry_name: str) -> str:
    return inputs[registry_name]["lineage_id"]


def _rebind_registry_artifact(artifact: dict, registry_name: str) -> None:
    if registry_name == "validated_phase_registry":
        normalized = {
            "registry_id": artifact["registry_id"],
            "architecture_binding": {
                "authority": artifact["architecture_authority"],
                "pipeline_version": artifact["pipeline_version"],
                "phase_registry_id": artifact["registry_id"],
            },
            "phases": artifact["phases"],
        }
        prefix = "validated-phase-registry"
    else:
        normalized = artifact["modules"]
        prefix = "validated-module-registry"
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    artifact["lineage_id"] = f"sha256:{digest}"
    artifact["artifact_id"] = f"{prefix}-{digest[:12]}"


def test_rejects_forged_partial_registries_even_with_recomputed_syntactic_lineage():
    inputs = valid_inputs()
    phases = inputs["validated_phase_registry"]
    phases["phases"] = phases["phases"][:1]
    phases["phase_count"] = 1
    _rebind_registry_artifact(phases, "validated_phase_registry")
    with pytest.raises(ContractValidationError, match="canonical 10-phase universe"):
        run_module(inputs, {})

    inputs = valid_inputs()
    modules = inputs["validated_module_registry"]
    modules["modules"] = modules["modules"][:5]
    modules["module_count"] = 5
    _rebind_registry_artifact(modules, "validated_module_registry")
    with pytest.raises(ContractValidationError, match="canonical active module universe"):
        run_module(inputs, {})


def test_rejects_forged_registry_validation_signals():
    inputs = valid_inputs()
    inputs["validated_module_registry"]["contract_hash_valid"] = False
    with pytest.raises(ContractValidationError, match="validation signals are incomplete"):
        run_module(inputs, {})


@pytest.mark.parametrize(
    "input_name",
    ["connection_matrix_yaml", "validated_phase_registry", "validated_module_registry"],
)
def test_rejects_symbolic_placeholders(input_name):
    inputs = valid_inputs()
    inputs[input_name] = {"source": input_name}
    with pytest.raises(ContractValidationError, match="matrix mapping|materialized artifact"):
        run_module(inputs, {})


def test_rejects_malformed_yaml(tmp_path):
    malformed = tmp_path / "matrix.yaml"
    malformed.write_text("module_io_matrix: [not-closed", encoding="utf-8")
    inputs = valid_inputs()
    inputs["connection_matrix_yaml"] = malformed
    with pytest.raises(ContractValidationError, match="invalid YAML for connection matrix"):
        run_module(inputs, {})


def test_rejects_unknown_modules_and_dependencies():
    inputs = valid_inputs()
    inputs["connection_matrix_yaml"]["module_io_matrix"][0]["module_id"] = "P0.S1.M99"
    with pytest.raises(ContractValidationError, match="unknown module_id"):
        run_module(inputs, {})

    inputs = valid_inputs()
    inputs["connection_matrix_yaml"]["module_io_matrix"][3]["consumes_from"]["modules"].append(
        "P0.S1.M99"
    )
    with pytest.raises(ContractValidationError, match="unknown or cross-phase module"):
        run_module(inputs, {})


def test_rejects_nonreciprocal_dependency_and_artifactless_edge():
    inputs = valid_inputs()
    inputs["connection_matrix_yaml"]["module_io_matrix"][3]["consumes_from"]["modules"].remove(
        "P0.S1.M03"
    )
    with pytest.raises(ContractValidationError, match="not reciprocal"):
        run_module(inputs, {})

    inputs = valid_inputs()
    inputs["connection_matrix_yaml"]["module_io_matrix"][2]["emits_to"]["artifacts"] = [
        "unrelated_control_report"
    ]
    with pytest.raises(ContractValidationError, match="no declared shared artifact"):
        run_module(inputs, {})


def test_rejects_consumed_artifact_without_producer_or_phase_input():
    inputs = valid_inputs()
    inputs["connection_matrix_yaml"]["module_io_matrix"][3]["consumes_from"]["artifacts"].append(
        "undeclared_control_report"
    )
    with pytest.raises(ContractValidationError, match="without declared producer or phase input"):
        run_module(inputs, {})


def test_rejects_duplicate_artifact_producers():
    inputs = valid_inputs()
    inputs["connection_matrix_yaml"]["module_io_matrix"][1]["emits_to"]["artifacts"].append(
        "validated_phase_registry"
    )
    with pytest.raises(ContractValidationError, match="multiple producers"):
        run_module(inputs, {})


def test_rejects_economic_payload_in_zero_trust_plane():
    inputs = valid_inputs()
    m04 = inputs["connection_matrix_yaml"]["module_io_matrix"][3]
    m04["consumes_from"]["artifacts"].append("predictions")
    m04["consumes_from"]["phase_inputs"].append("predictions")
    with pytest.raises(ContractValidationError, match="economic payload artifacts"):
        run_module(inputs, {})


@pytest.mark.parametrize(
    "container,field",
    [
        ("connection_matrix_yaml", "future_return"),
        ("validated_phase_registry", "trade_decision"),
        ("validated_module_registry", "portfolio_weight"),
    ],
)
def test_rejects_forbidden_fields_recursively(container, field):
    inputs = valid_inputs()
    inputs[container]["nested"] = [{"deeper": {field: "forbidden"}}]
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(inputs, {})


def test_rejects_invalid_registry_identity_and_contract_binding():
    inputs = valid_inputs()
    inputs["validated_module_registry"]["registry_id"] = "module_registry_v15"
    with pytest.raises(ContractValidationError, match="registry version is incompatible"):
        run_module(inputs, {})

    inputs = valid_inputs()
    inputs["connection_matrix_yaml"]["module_io_matrix"][3]["module_contract"] = (
        "modules/P0_S1_M04_wrong.yaml"
    )
    with pytest.raises(ContractValidationError, match="does not match registry"):
        run_module(inputs, {})


def test_output_conforms_to_enriched_schema_and_invalid_outputs_are_rejected():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "validated_connection_matrix.schema.yaml").read_text(
            encoding="utf-8"
        )
    )
    artifact = run_module(
        valid_inputs(), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["validated_connection_matrix"]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(artifact) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    assert schema["properties"]["module_io_matrix"]["items"]["additionalProperties"] is False

    invalid = deepcopy(artifact)
    invalid["unexpected_output"] = True
    with pytest.raises(ContractValidationError, match="output schema extra fields"):
        _validate_artifact(invalid)

    invalid = deepcopy(artifact)
    invalid["module_io_matrix"][0]["nested"] = {"rank_score": 1}
    with pytest.raises(ContractValidationError, match="output schema extra fields|forbidden output"):
        _validate_artifact(invalid)


def test_rejects_non_mapping_config_and_missing_inputs():
    with pytest.raises(ContractValidationError, match="config must be a dict"):
        run_module(valid_inputs(), [])
    with pytest.raises(ContractValidationError, match="missing required inputs"):
        run_module({}, {})
