from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import re

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_baseline import (
    canonical_authorities,
    canonical_phase_ids,
    canonical_phases,
    canonical_subphase_ids,
    expected_subphase_counts,
    forbidden_fields,
    registry_baseline,
)
from ._p0_s1_common import (
    created_at,
    find_forbidden_fields,
    load_mapping_input,
    module_result,
    normalized_version,
    require_inputs,
    stable_digest,
    validate_lineage_id,
    validate_output,
    workspace_root,
)


MODULE_ID = "P0.S1.M02"
MODULE_NAME = "subphase_registry_loader"
CONTRACT = "P0_S1_M02_subphase_registry_loader.yaml"
REQUIRED_INPUTS = ["validated_phase_registry", "subphase_registry_yaml"]
OUTPUT_NAME = "validated_subphase_registry"


def _load_registry(value: Any) -> tuple[dict[str, Any], str]:
    try:
        return load_mapping_input(
            value,
            label="subphase registry",
            collection_key="subphases",
            symbolic_name="subphase_registry_yaml",
        )
    except ContractValidationError as exc:
        message = str(exc).replace(
            "subphase_registry_yaml must be a mapping",
            "subphase_registry_yaml must be a registry mapping",
        )
        raise ContractValidationError(message) from exc


def _validate_phase_registry(value: Any) -> tuple[set[str], str]:
    if not isinstance(value, dict) or set(value) == {"source"}:
        raise ContractValidationError("validated_phase_registry must be a materialized artifact")
    required = {"registry_id", "pipeline_version", "lineage_id", "phase_count", "phases"}
    missing = sorted(required.difference(value))
    if missing:
        raise ContractValidationError(f"validated_phase_registry missing fields: {missing}")

    phase_policy = registry_baseline("phase")
    if value["registry_id"] != phase_policy["registry_id"]:
        raise ContractValidationError("validated_phase_registry registry version is incompatible")
    if normalized_version(value["pipeline_version"]) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("validated_phase_registry pipeline version is incompatible")
    lineage_id = validate_lineage_id(value.get("lineage_id"), "validated_phase_registry")

    phases = value.get("phases")
    if not isinstance(phases, list) or not phases or not all(isinstance(item, dict) for item in phases):
        raise ContractValidationError("validated_phase_registry phases must be mappings")
    phase_ids = [item.get("phase_id") for item in phases]
    if not all(isinstance(item, str) and item for item in phase_ids):
        raise ContractValidationError("validated_phase_registry contains an invalid phase_id")
    if len(phase_ids) != len(set(phase_ids)):
        raise ContractValidationError("validated_phase_registry contains duplicate phase_id values")
    if set(phase_ids) != canonical_phase_ids() or value["phase_count"] != len(canonical_phase_ids()):
        raise ContractValidationError("validated_phase_registry must cover exactly P0-P9")
    if phases != canonical_phases():
        raise ContractValidationError(
            "validated_phase_registry does not match canonical packages and planes"
        )

    authority = value.get("architecture_authority")
    if authority not in canonical_authorities():
        raise ContractValidationError("validated_phase_registry architecture authority is invalid")
    normalized = {
        "registry_id": value["registry_id"],
        "architecture_binding": {
            "authority": authority,
            "pipeline_version": PIPELINE_VERSION,
            "phase_registry_id": value["registry_id"],
        },
        "phases": phases,
    }
    if lineage_id != f"sha256:{stable_digest(normalized)}":
        raise ContractValidationError("validated_phase_registry lineage_id does not match content")
    if value.get("promotion_blocked") is not True:
        raise ContractValidationError("validated_phase_registry must remain promotion_blocked")
    return set(phase_ids), lineage_id


def _validate_provenance(value: Any, phase_ids: set[str], allow_external_missing: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractValidationError("provenance must be a mapping")
    expected_authority = next(
        authority for authority in canonical_authorities() if authority != "global_master"
    )
    if value.get("authority") != expected_authority:
        raise ContractValidationError("provenance authority is not canonical")
    sources = value.get("derived_from")
    if not isinstance(sources, list) or not all(isinstance(item, dict) for item in sources):
        raise ContractValidationError("provenance.derived_from must contain source mappings")
    source_phase_ids = [item.get("phase_id") for item in sources]
    if len(source_phase_ids) != len(set(source_phase_ids)) or set(source_phase_ids) != phase_ids:
        raise ContractValidationError("provenance must contain exactly one source for each phase")
    normalized = [
        item if allow_external_missing and item.get("phase_id") != "P0" else _validate_provenance_source(item)
        for item in sources
    ]
    return {
        "authority": expected_authority,
        "derived_from": sorted(normalized, key=lambda item: item["phase_id"]),
    }


def _validate_provenance_source(source: dict[str, Any]) -> dict[str, str]:
    phase_id = source.get("phase_id")
    source_path = source.get("source_path")
    expected_hash = source.get("sha256")
    if not isinstance(source_path, str) or not source_path.strip():
        raise ContractValidationError(f"provenance source_path is missing for {phase_id}")
    if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
        raise ContractValidationError(f"provenance sha256 is invalid for {phase_id}")

    root = workspace_root().resolve()
    resolved = (root / source_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ContractValidationError(
            f"provenance source escapes workspace for {phase_id}: {source_path}"
        ) from exc
    if not resolved.is_file() or resolved.name != "SUBPHASES.md":
        raise ContractValidationError(
            f"provenance source does not exist for {phase_id}: {source_path}"
        )
    actual_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise ContractValidationError(f"provenance hash mismatch for {phase_id}")
    return {"phase_id": str(phase_id), "source_path": source_path, "sha256": expected_hash}


def _normalize_subphases(subphases: Any, phase_ids: set[str], p0_scope: bool = False) -> list[dict[str, str]]:
    if not isinstance(subphases, list) or not subphases or not all(isinstance(item, dict) for item in subphases):
        raise ContractValidationError("subphase registry must contain subphase mappings")
    subphase_ids = [item.get("subphase_id") for item in subphases]
    valid_ids = all(
        isinstance(item, str) and re.fullmatch(r"P[0-9]+\.S[0-9]+", item)
        for item in subphase_ids
    )
    if not valid_ids or len(subphase_ids) != len(set(subphase_ids)):
        raise ContractValidationError("subphase_id_unique validation failed")
    parents_valid = all(
        isinstance(item.get("phase_id"), str)
        and item["phase_id"] in phase_ids
        and item["subphase_id"].split(".S", 1)[0] == item["phase_id"]
        for item in subphases
    )
    if not parents_valid:
        raise ContractValidationError("subphase_belongs_to_existing_phase validation failed")
    if set(subphase_ids) != canonical_subphase_ids():
        raise ContractValidationError("exact_subphase_set validation failed")
    return sorted(
        ({"subphase_id": item["subphase_id"], "phase_id": item["phase_id"]} for item in subphases),
        key=lambda item: (int(item["phase_id"][1:]), int(item["subphase_id"].split(".S", 1)[1])),
    )



def _validate_registry_identity(
    registry: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    policy = registry_baseline("subphase")
    runtime_version = str(config.get("pipeline_version") or PIPELINE_VERSION)
    if normalized_version(runtime_version) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("pipeline version is incompatible")
    if registry.get("registry_id") != policy["registry_id"]:
        raise ContractValidationError("subphase registry version is incompatible")
    if normalized_version(registry.get("schema_version")) != normalized_version(policy["schema_version"]):
        raise ContractValidationError("subphase registry schema version is incompatible")
    return policy


def _build_artifact(
    *,
    policy: dict[str, Any],
    source_path: str,
    phase_ids: set[str],
    phase_lineage: str,
    subphases: list[dict[str, str]],
    provenance: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    normalized = {
        "registry_id": policy["registry_id"],
        "schema_version": policy["schema_version"],
        "phase_registry_lineage_id": phase_lineage,
        "subphases": subphases,
        "provenance": provenance,
    }
    digest = stable_digest(normalized)
    return {
        "artifact_id": f"validated-subphase-registry-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "source_path": source_path,
        "registry_id": policy["registry_id"],
        "source_schema_version": policy["schema_version"],
        "phase_registry_lineage_id": phase_lineage,
        "phase_count": len(phase_ids),
        "subphase_count": len(subphases),
        "subphases": subphases,
        "provenance": provenance,
        "subphase_id_unique": True,
        "subphase_belongs_to_existing_phase": True,
        "exact_subphase_set": True,
        "provenance_valid": True,
        "registry_version_compatible": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }

def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_inputs(inputs, config, REQUIRED_INPUTS)
    leaked = find_forbidden_fields(inputs, forbidden_fields())
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")

    phase_ids, phase_lineage = _validate_phase_registry(inputs["validated_phase_registry"])
    p0_scope = str(config.get("release_scope", "")).upper() == "P0_TECHNICAL_CLOSURE"
    active_phase_ids = phase_ids
    registry, source_path = _load_registry(inputs["subphase_registry_yaml"])
    policy = _validate_registry_identity(registry, config)
    normalized_subphases = _normalize_subphases(registry.get("subphases"), active_phase_ids, p0_scope)
    expected_subphase_count = int(policy["subphase_count"])
    if len(normalized_subphases) != expected_subphase_count:
        raise ContractValidationError("exact_subphase_set validation failed")
    actual_counts = {phase: 0 for phase in active_phase_ids}
    for item in normalized_subphases:
        actual_counts[item["phase_id"]] += 1
    if actual_counts != expected_subphase_counts():
        raise ContractValidationError("exact_subphase_set validation failed")
    provenance_input = registry.get("provenance")
    provenance = _validate_provenance(provenance_input, active_phase_ids, allow_external_missing=p0_scope)
    artifact = _build_artifact(
        policy=policy,
        source_path=source_path,
        phase_ids=phase_ids,
        phase_lineage=phase_lineage,
        subphases=normalized_subphases,
        provenance=provenance,
        config=config,
    )
    validate_output(
        artifact,
        schema_name="validated_subphase_registry.schema.yaml",
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


EXPECTED_REGISTRY_ID = str(registry_baseline("subphase")["registry_id"])
EXPECTED_SCHEMA_VERSION = str(registry_baseline("subphase")["schema_version"])
EXPECTED_PHASE_COUNTS = expected_subphase_counts()
EXPECTED_SUBPHASE_IDS = canonical_subphase_ids()
