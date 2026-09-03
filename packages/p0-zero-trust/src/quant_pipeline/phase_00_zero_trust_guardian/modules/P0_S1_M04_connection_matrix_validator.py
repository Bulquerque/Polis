from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_baseline import architecture_baseline, forbidden_fields
from ._p0_s1_common import (
    created_at,
    find_forbidden_fields,
    module_result,
    require_inputs,
    stable_digest,
    validate_output,
)
from ._p0_s1_registry_attestation import registry_maps
from ._p0_s1_topology import load_connection_matrix, validate_topology


MODULE_ID = "P0.S1.M04"
MODULE_NAME = "connection_matrix_validator"
CONTRACT = "P0_S1_M04_connection_matrix_validator.yaml"
REQUIRED_INPUTS = [
    "connection_matrix_yaml",
    "validated_phase_registry",
    "validated_module_registry",
]
OUTPUT_NAME = "validated_connection_matrix"


def _validate_artifact(artifact: dict[str, Any]) -> None:
    validate_output(
        artifact,
        schema_name="validated_connection_matrix.schema.yaml",
        artifact_name=OUTPUT_NAME,
        forbidden_fields=forbidden_fields(),
    )


def _build_artifact(
    *,
    phase_id: str,
    rows: list[dict[str, Any]],
    connections: list[dict[str, str]],
    source_path: str,
    phase_registry_lineage_id: str,
    module_registry_lineage_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    baseline = architecture_baseline()
    normalized = {
        "phase": phase_id,
        "rc": baseline["rc"],
        "contract": baseline["matrix"]["contract"],
        "format": baseline["matrix"]["format"],
        "phase_registry_lineage_id": phase_registry_lineage_id,
        "module_registry_lineage_id": module_registry_lineage_id,
        "module_io_matrix": rows,
        "connections": connections,
    }
    digest = stable_digest(normalized)
    return {
        "artifact_id": f"validated-connection-matrix-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "source_path": source_path,
        **normalized,
        "module_count": len(rows),
        "connection_count": len(connections),
        "registry_identity_valid": True,
        "dependency_reciprocity_valid": True,
        "artifact_flow_valid": True,
        "economic_connections_allowed_only": True,
        "zero_trust_plane_metadata_only": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_inputs(inputs, config, REQUIRED_INPUTS)
    leaked = find_forbidden_fields(inputs, forbidden_fields())
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")

    phases, modules = registry_maps(
        inputs["validated_phase_registry"],
        inputs["validated_module_registry"],
        config.get("release_scope"),
    )
    matrix, source_path = load_connection_matrix(inputs["connection_matrix_yaml"])
    phase_id, rows, connections = validate_topology(matrix, phases, modules)
    artifact = _build_artifact(
        phase_id=phase_id,
        rows=rows,
        connections=connections,
        source_path=source_path,
        phase_registry_lineage_id=inputs["validated_phase_registry"]["lineage_id"],
        module_registry_lineage_id=inputs["validated_module_registry"]["lineage_id"],
        config=config,
    )
    _validate_artifact(artifact)
    return module_result(
        module_id=MODULE_ID,
        module_name=MODULE_NAME,
        contract=CONTRACT,
        required_inputs=REQUIRED_INPUTS,
        output_name=OUTPUT_NAME,
        artifact=artifact,
    )
