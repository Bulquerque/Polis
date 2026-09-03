from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_baseline import (
    canonical_authorities,
    canonical_phases,
    forbidden_fields,
    registry_baseline,
)
from ._p0_s1_common import (
    created_at,
    find_forbidden_fields,
    load_mapping_input,
    load_yaml_mapping,
    module_result,
    normalized_version,
    require_inputs,
    stable_digest,
    validate_output,
    validate_schema_value,
)


MODULE_ID = "P0.S1.M01"
MODULE_NAME = "phase_registry_loader"
CONTRACT = "P0_S1_M01_phase_registry_loader.yaml"
REQUIRED_INPUTS = ["phase_registry_yaml", "global_architecture_config"]
OUTPUT_NAME = "validated_phase_registry"


def _load_phase_registry(value: Any) -> tuple[dict[str, Any], str]:
    try:
        return load_mapping_input(
            value,
            label="phase registry",
            collection_key="phases",
            symbolic_name="phase_registry_yaml",
        )
    except ContractValidationError as exc:
        message = str(exc).replace(
            "phase_registry_yaml must be a mapping",
            "phase_registry_yaml must be a registry mapping",
        )
        raise ContractValidationError(message) from exc


def _load_architecture_config(value: Any) -> tuple[dict[str, Any], str]:
    return load_mapping_input(
        value,
        label="architecture config",
        symbolic_name="global_architecture_config",
    )


def _validate_phase_shape(phases: Any) -> list[dict[str, str]]:
    if not isinstance(phases, list) or not phases or not all(isinstance(item, dict) for item in phases):
        raise ContractValidationError("phase registry must contain phase mappings")

    phase_ids = [item.get("phase_id") for item in phases]
    if not all(isinstance(value, str) and value for value in phase_ids) or len(phase_ids) != len(set(phase_ids)):
        raise ContractValidationError("phase_id_unique validation failed")
    if not all(isinstance(item.get("plane"), str) and item["plane"].strip() for item in phases):
        raise ContractValidationError("phase_type_declared validation failed")
    if not all(isinstance(item.get("package_name"), str) and item["package_name"].strip() for item in phases):
        raise ContractValidationError("package_name_declared validation failed")

    if any(set(item) != {"phase_id", "package_name", "plane"} for item in phases):
        raise ContractValidationError(
            "phase registry does not match the canonical P0-P9 identities, packages, and planes"
        )
    normalized = [
        {
            "phase_id": str(item["phase_id"]),
            "package_name": str(item["package_name"]),
            "plane": str(item["plane"]),
        }
        for item in phases
    ]
    if normalized != canonical_phases():
        raise ContractValidationError(
            "phase registry does not match the canonical P0-P9 identities, packages, and planes"
        )
    return normalized


def _validate_architecture_config(
    architecture: dict[str, Any], registry_id: str
) -> str:
    if not architecture or set(architecture) == {"source"}:
        raise ContractValidationError("global_architecture_config is a symbolic placeholder")
    authority = architecture.get("authority")
    if not isinstance(authority, str) or not authority.strip():
        raise ContractValidationError(
            "global_architecture_config.authority must be a non-empty string"
        )
    normalized_authority = authority.strip().replace("\\", "/").rstrip("/")
    if normalized_authority not in canonical_authorities():
        raise ContractValidationError(
            f"global_architecture_config.authority is not canonical: {authority}"
        )

    declared_version = architecture.get("pipeline_version")
    if declared_version in (None, ""):
        raise ContractValidationError(
            "global_architecture_config.pipeline_version must bind the canonical release"
        )
    if normalized_version(declared_version) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError(
            "global_architecture_config version is incompatible with " + PIPELINE_VERSION
        )
    if architecture.get("phase_registry_id") != registry_id:
        raise ContractValidationError(
            "global_architecture_config registry binding does not match phase registry"
        )
    return normalized_authority


def _build_artifact(
    *,
    phases: list[dict[str, str]],
    registry_id: str,
    source_path: str,
    architecture_source_path: str,
    architecture_authority: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    normalized = {
        "registry_id": registry_id,
        "architecture_binding": {
            "authority": architecture_authority,
            "pipeline_version": PIPELINE_VERSION,
            "phase_registry_id": registry_id,
        },
        "phases": phases,
    }
    digest = stable_digest(normalized)
    return {
        "artifact_id": f"validated-phase-registry-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "source_path": source_path,
        "architecture_source_path": architecture_source_path,
        "registry_id": registry_id,
        "architecture_authority": architecture_authority,
        "phase_count": len(phases),
        "phases": phases,
        "phase_id_unique": True,
        "phase_type_declared": True,
        "registry_id_declared": True,
        "package_name_declared": True,
        "global_architecture_config_valid": True,
        "registry_version_compatible": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_inputs(inputs, config, REQUIRED_INPUTS)
    leaked = find_forbidden_fields(inputs, forbidden_fields())
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")

    registry, source_path = _load_phase_registry(inputs["phase_registry_yaml"])
    registry_id = registry.get("registry_id")
    if not isinstance(registry_id, str) or not registry_id.strip():
        raise ContractValidationError("registry_id_declared validation failed")
    phases = _validate_phase_shape(registry.get("phases"))
    expected_id = str(registry_baseline("phase")["registry_id"])
    if registry_id != expected_id:
        raise ContractValidationError(
            f"registry version is incompatible: {registry_id}; expected {expected_id}"
        )
    runtime_version = str(config.get("pipeline_version") or PIPELINE_VERSION)
    if normalized_version(runtime_version) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError(
            f"pipeline version is incompatible: {runtime_version}; expected {PIPELINE_VERSION}"
        )

    if set(registry) != {"registry_id", "phases"}:
        raise ContractValidationError(
            "phase registry does not match the canonical P0-P9 identities, packages, and planes"
        )
    architecture, architecture_source = _load_architecture_config(
        inputs["global_architecture_config"]
    )
    authority = _validate_architecture_config(architecture, registry_id)
    artifact = _build_artifact(
        phases=phases,
        registry_id=registry_id,
        source_path=source_path,
        architecture_source_path=architecture_source,
        architecture_authority=authority,
        config=config,
    )
    validate_output(
        artifact,
        schema_name="validated_phase_registry.schema.yaml",
        artifact_name=OUTPUT_NAME,
        forbidden_fields=forbidden_fields(),
    )
    return module_result(
        module_id=MODULE_ID,
        module_name=MODULE_NAME,
        contract=CONTRACT,
        required_inputs=REQUIRED_INPUTS,
        output_name=OUTPUT_NAME,
        artifact=artifact,
    )


# Compatibility exports used by historical tests and downstream adapters.
EXPECTED_REGISTRY_ID = str(registry_baseline("phase")["registry_id"])
EXPECTED_PHASES = canonical_phases()


# Deprecated compatibility aliases. Other P0 subphases still import these names;
# they delegate to the shared S1 infrastructure and can be migrated incrementally.
_created_at = created_at
_load_yaml_mapping = load_yaml_mapping
_normalized_version = normalized_version
_validate_schema_value = validate_schema_value


def _find_forbidden_fields(value: Any, path: str = "inputs") -> list[str]:
    return find_forbidden_fields(value, forbidden_fields(), path)
