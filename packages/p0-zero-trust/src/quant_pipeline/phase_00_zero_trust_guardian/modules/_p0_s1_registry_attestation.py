from __future__ import annotations

from typing import Any
import re

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ._p0_s1_baseline import (
    canonical_module_ids,
    canonical_phases,
    registry_baseline,
)
from ._p0_s1_common import (
    MODULE_ID_PATTERN,
    load_yaml_mapping,
    normalized_version,
    stable_digest,
    validate_lineage_id,
)


def registry_maps(
    validated_phase_registry: Any,
    validated_module_registry: Any,
    release_scope: str | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    phases = _phase_map(validated_phase_registry)
    modules = _module_map(validated_module_registry, phases, release_scope)
    return phases, modules


def _phase_map(value: Any) -> dict[str, str]:
    rows = _materialized_rows(
        value,
        label="validated_phase_registry",
        registry_id=str(registry_baseline("phase")["registry_id"]),
        collection="phases",
    )
    _require_attested_artifact(
        value,
        label="validated_phase_registry",
        schema_name="validated_phase_registry.schema.yaml",
        required_true={
            "phase_id_unique",
            "phase_type_declared",
            "registry_id_declared",
            "package_name_declared",
            "global_architecture_config_valid",
            "registry_version_compatible",
        },
    )
    expected = canonical_phases()
    if rows != expected:
        raise ContractValidationError(
            "validated_phase_registry must contain the canonical 10-phase universe"
        )
    authority = value.get("architecture_authority")
    if not isinstance(authority, str) or not authority:
        raise ContractValidationError("validated_phase_registry architecture_authority is invalid")
    normalized = {
        "registry_id": value["registry_id"],
        "architecture_binding": {
            "authority": authority,
            "pipeline_version": PIPELINE_VERSION,
            "phase_registry_id": value["registry_id"],
        },
        "phases": rows,
    }
    _assert_lineage(value, "validated_phase_registry", normalized, "validated-phase-registry")
    phases = {row["phase_id"]: row["plane"] for row in rows}
    if [phase for phase, plane in phases.items() if plane == "zero_trust_control"] != ["P0"]:
        raise ContractValidationError(
            "validated_phase_registry must declare only P0 as zero_trust_control"
        )
    return phases


def _module_map(value: Any, phases: dict[str, str], release_scope: str | None = None) -> dict[str, dict[str, str]]:
    rows = _materialized_rows(
        value,
        label="validated_module_registry",
        registry_id=str(registry_baseline("module")["registry_id"]),
        collection="modules",
    )
    _require_attested_artifact(
        value,
        label="validated_module_registry",
        schema_name="validated_module_registry.schema.yaml",
        required_true={
            "module_id_unique",
            "module_has_contract",
            "module_parent_valid",
            "contract_identity_valid",
            "contract_hash_valid",
            "registry_version_compatible",
        },
    )
    modules: dict[str, dict[str, str]] = {}
    required = {
        "module_id",
        "module_name",
        "phase_id",
        "subphase_id",
        "contract_path",
        "contract_sha256",
    }
    for index, row in enumerate(rows):
        module_id, normalized = _validate_module_row(row, index, phases, required)
        if module_id in modules:
            raise ContractValidationError(
                f"validated_module_registry contains invalid or duplicate module_id: {module_id}"
            )
        modules[module_id] = normalized
    expected_ids = {
        module_id
        for module_id in canonical_module_ids()
        if str(release_scope or "").upper() != "P0_TECHNICAL_CLOSURE"
        or module_id.startswith("P0.")
    }
    if set(modules) != expected_ids:
        raise ContractValidationError(
            "validated_module_registry must contain the canonical active module universe"
        )
    _assert_lineage(value, "validated_module_registry", rows, "validated-module-registry")
    return modules


def _validate_module_row(
    row: dict[str, Any], index: int, phases: dict[str, str], required: set[str]
) -> tuple[str, dict[str, str]]:
    if set(row) != required:
        missing = sorted(required.difference(row))
        extra = sorted(set(row).difference(required))
        raise ContractValidationError(
            f"validated_module_registry module {index} has invalid fields; missing={missing}, extra={extra}"
        )
    module_id = str(row["module_id"])
    match = MODULE_ID_PATTERN.fullmatch(module_id)
    if match is None:
        raise ContractValidationError(f"validated_module_registry contains invalid module_id: {module_id}")
    phase_id = f"P{int(match.group('phase'))}"
    subphase_id = f"{phase_id}.S{int(match.group('subphase'))}"
    if row["phase_id"] != phase_id or phase_id not in phases:
        raise ContractValidationError(f"registered module has invalid phase parent: {module_id}")
    if row["subphase_id"] != subphase_id:
        raise ContractValidationError(f"registered module has invalid subphase parent: {module_id}")
    return module_id, {key: str(row[key]) for key in required}


def _materialized_rows(
    value: Any,
    *,
    label: str,
    registry_id: str,
    collection: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or set(value) == {"source"}:
        raise ContractValidationError(f"{label} must be a materialized artifact")
    if value.get("registry_id") != registry_id:
        raise ContractValidationError(f"{label} registry version is incompatible")
    if normalized_version(value.get("pipeline_version")) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError(f"{label} pipeline version is incompatible")
    validate_lineage_id(value.get("lineage_id"), label)
    if value.get("promotion_blocked") is not True:
        raise ContractValidationError(f"{label} must remain promotion_blocked")
    rows = value.get(collection)
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ContractValidationError(f"{label}.{collection} must contain mappings")
    count_name = "phase_count" if collection == "phases" else "module_count"
    if value.get(count_name) != len(rows):
        raise ContractValidationError(f"{label}.{count_name} does not match materialized rows")
    return rows


def _require_attested_artifact(
    value: dict[str, Any],
    *,
    label: str,
    schema_name: str,
    required_true: set[str],
) -> None:
    schema = load_yaml_mapping(SCHEMA_ROOT / schema_name, f"{label} schema")
    expected_fields = set(schema.get("properties", {}))
    if set(value) != expected_fields:
        missing = sorted(expected_fields.difference(value))
        extra = sorted(set(value).difference(expected_fields))
        raise ContractValidationError(
            f"{label} artifact shape is invalid; missing={missing}, extra={extra}"
        )
    invalid = sorted(field for field in required_true if value.get(field) is not True)
    if invalid:
        raise ContractValidationError(
            f"{label} validation signals are incomplete; missing=[], invalid={invalid}"
        )
    if value.get("validation_evidence_status") != "domain_oracle_pass_pending_independent_judge":
        raise ContractValidationError(f"{label} validation evidence status is incompatible")


def _assert_lineage(
    value: dict[str, Any],
    label: str,
    normalized: Any,
    prefix: str,
) -> None:
    digest = stable_digest(normalized)
    if value.get("lineage_id") != f"sha256:{digest}":
        raise ContractValidationError(f"{label} lineage_id does not bind materialized content")
    if value.get("artifact_id") != f"{prefix}-{digest[:12]}":
        raise ContractValidationError(f"{label} artifact_id does not bind materialized content")
