from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import re

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_baseline import forbidden_fields, registry_baseline
from ._p0_s1_common import (
    MODULE_ID_PATTERN,
    created_at,
    find_forbidden_fields,
    load_mapping_input,
    load_yaml_mapping,
    module_result,
    require_inputs,
    stable_digest,
    validate_output,
    workspace_root,
)


MODULE_ID = "P0.S1.M03"
MODULE_NAME = "module_registry_loader"
CONTRACT = "P0_S1_M03_module_registry_loader.yaml"
REQUIRED_INPUTS = ["validated_phase_registry", "validated_subphase_registry", "module_registry_yaml"]
OUTPUT_NAME = "validated_module_registry"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _load_registry(value: Any) -> tuple[dict[str, Any], str]:
    try:
        return load_mapping_input(
            value,
            label="module registry",
            collection_key="modules",
            symbolic_name="module_registry_yaml",
        )
    except ContractValidationError as exc:
        message = str(exc).replace(
            "module_registry_yaml must be a mapping",
            "module_registry_yaml must be a registry mapping",
        )
        raise ContractValidationError(message) from exc


def _parent_maps(
    validated_phase_registry: Any,
    validated_subphase_registry: Any,
) -> tuple[set[str], dict[str, str]]:
    if not isinstance(validated_phase_registry, dict):
        raise ContractValidationError("validated_phase_registry must be a mapping")
    if not isinstance(validated_subphase_registry, dict):
        raise ContractValidationError("validated_subphase_registry must be a mapping")
    phases = validated_phase_registry.get("phases")
    subphases = validated_subphase_registry.get("subphases")
    if not isinstance(phases, list) or not phases:
        raise ContractValidationError("validated_phase_registry must contain phases")
    if not isinstance(subphases, list) or not subphases:
        raise ContractValidationError("validated_subphase_registry must contain subphases")

    phase_ids = _phase_ids(phases)
    subphase_map = _subphase_map(subphases, phase_ids)
    return phase_ids, subphase_map


def _phase_ids(phases: list[Any]) -> set[str]:
    values: list[str] = []
    for item in phases:
        if not isinstance(item, dict) or not isinstance(item.get("phase_id"), str):
            raise ContractValidationError("validated_phase_registry contains an invalid phase")
        values.append(item["phase_id"])
    if len(values) != len(set(values)):
        raise ContractValidationError("validated_phase_registry contains duplicate phase_id")
    return set(values)


def _subphase_map(subphases: list[Any], phase_ids: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in subphases:
        if not isinstance(item, dict):
            raise ContractValidationError("validated_subphase_registry contains an invalid subphase")
        subphase_id = item.get("subphase_id")
        phase_id = item.get("phase_id")
        if not isinstance(subphase_id, str) or not isinstance(phase_id, str):
            raise ContractValidationError("subphase_id and phase_id must be strings")
        if subphase_id in result:
            raise ContractValidationError(f"duplicate subphase_id: {subphase_id}")
        if phase_id not in phase_ids:
            raise ContractValidationError(f"subphase parent phase does not exist: {subphase_id}")
        if subphase_id.rsplit(".S", 1)[0] != phase_id:
            raise ContractValidationError(f"subphase parent identity mismatch: {subphase_id}")
        result[subphase_id] = phase_id
    return result


def _resolve_contract(contract_path: Any) -> tuple[Path, str]:
    if not isinstance(contract_path, str) or not contract_path or "\\" in contract_path:
        raise ContractValidationError(
            "contract_path must be a canonical repository-relative POSIX path"
        )
    pure_path = PurePosixPath(contract_path)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ContractValidationError(
            f"contract_path escapes repository authority: {contract_path}"
        )
    root = workspace_root().resolve()
    candidate = (root / Path(*pure_path.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractValidationError(f"contract_path is outside repository: {contract_path}") from exc
    if candidate.parent.name != "modules" or candidate.suffix != ".yaml":
        raise ContractValidationError(
            f"contract_path is not an internal module contract: {contract_path}"
        )
    if not candidate.is_file():
        raise ContractValidationError(f"module contract does not exist: {contract_path}")
    return candidate, pure_path.as_posix()


def _validate_registry(
    registry: dict[str, Any],
    phase_ids: set[str],
    subphase_map: dict[str, str],
    config: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    policy = registry_baseline("module")
    p0_scope = str((config or {}).get("release_scope", "")).upper() == "P0_TECHNICAL_CLOSURE"
    expected_count = 40 if p0_scope else int(policy["module_count"])
    if registry.get("registry_id") != policy["registry_id"]:
        raise ContractValidationError(
            f"registry version is incompatible: {registry.get('registry_id')!r}"
        )
    if registry.get("hash_algorithm") != "sha256":
        raise ContractValidationError("module registry hash_algorithm must be sha256")
    declared_count = registry.get("module_count")
    if (not p0_scope and declared_count != expected_count) or (
        p0_scope and declared_count != int(policy["module_count"])
    ):
        raise ContractValidationError(
            f"module registry module_count must be {int(policy['module_count'])}"
        )
    modules = registry.get("modules")
    if not isinstance(modules, list):
        raise ContractValidationError("module registry must contain a modules list")
    if p0_scope:
        modules = [item for item in modules if isinstance(item, dict) and item.get("phase_id") == "P0"]
    if len(modules) != expected_count:
        raise ContractValidationError(f"module registry must contain exactly {expected_count} modules")
    normalized = [
        _validate_registry_entry(item, index, phase_ids, subphase_map)
        for index, item in enumerate(modules)
    ]
    _validate_uniqueness(normalized)
    return normalized


def _validate_registry_entry(
    item: Any,
    index: int,
    phase_ids: set[str],
    subphase_map: dict[str, str],
) -> dict[str, str]:
    if not isinstance(item, dict):
        raise ContractValidationError(f"module registry entry {index} must be a mapping")
    required = {
        "module_id", "module_name", "phase_id", "subphase_id",
        "contract_path", "contract_sha256",
    }
    missing = sorted(required.difference(item))
    extra = sorted(set(item).difference(required))
    if missing:
        raise ContractValidationError(f"module registry entry {index} missing fields: {missing}")
    if extra:
        raise ContractValidationError(f"module registry entry {index} has extra fields: {extra}")
    identity = _validate_module_identity(item, index, phase_ids, subphase_map)
    contract_file, canonical_path = _resolve_contract(item["contract_path"])
    _validate_contract_binding(identity, contract_file, canonical_path, item["contract_sha256"])
    return {**identity, "contract_path": canonical_path, "contract_sha256": item["contract_sha256"]}


def _validate_module_identity(
    item: dict[str, Any],
    index: int,
    phase_ids: set[str],
    subphase_map: dict[str, str],
) -> dict[str, str]:
    values = [item[key] for key in ("module_id", "module_name", "phase_id", "subphase_id")]
    if not all(isinstance(value, str) and value for value in values):
        raise ContractValidationError(f"module registry entry {index} has invalid identity fields")
    module_id, module_name, phase_id, subphase_id = values
    match = MODULE_ID_PATTERN.fullmatch(module_id)
    if match is None:
        raise ContractValidationError(f"invalid module_id: {module_id}")
    expected_phase = f"P{int(match.group('phase'))}"
    expected_subphase = f"{expected_phase}.S{int(match.group('subphase'))}"
    if phase_id != expected_phase or phase_id not in phase_ids:
        raise ContractValidationError(f"module parent phase is invalid: {module_id}")
    if subphase_id != expected_subphase or subphase_map.get(subphase_id) != phase_id:
        raise ContractValidationError(f"module parent subphase is invalid: {module_id}")
    digest = item["contract_sha256"]
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise ContractValidationError(f"invalid contract_sha256 for {module_id}")
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase_id": phase_id,
        "subphase_id": subphase_id,
    }


def _validate_contract_binding(
    identity: dict[str, str],
    contract_file: Path,
    canonical_path: str,
    expected_digest: str,
) -> None:
    module_id = identity["module_id"]
    module_name = identity["module_name"]
    phase_id = identity["phase_id"]
    subphase_id = identity["subphase_id"]
    match = MODULE_ID_PATTERN.fullmatch(module_id)
    assert match is not None
    parts = PurePosixPath(canonical_path).parts
    if len(parts) < 4 or not parts[0].startswith(f"phase_{int(match.group('phase')):02d}_"):
        raise ContractValidationError(f"contract package phase mismatch for {module_id}")
    expected_filename = f"{module_id.replace('.', '_')}_{module_name}.yaml"
    if contract_file.name != expected_filename:
        raise ContractValidationError(f"contract filename identity mismatch for {module_id}")
    contract = load_yaml_mapping(contract_file, f"contract for {module_id}")
    phase_name = {
        "P1": "phase_01_ingestion", "P2": "phase_02_quality_pit", "P3": "phase_03_agents_rag_memory",
        "P4": "phase_04_feature_base", "P5": "phase_05_underlying_forecasts", "P6": "phase_06_candidate_generation",
        "P7": "phase_07_ranking", "P8": "phase_08_portfolio_backtest", "P9": "phase_09_audit_learning",
    }.get(phase_id, phase_id)
    if (
        contract.get("module_id") != module_id
        or contract.get("module_name") != module_name
        or contract.get("subphase") != subphase_id
        or contract.get("phase") not in {phase_id, phase_name}
    ):
        raise ContractValidationError(f"contract YAML identity mismatch for {module_id}")
    actual_digest = hashlib.sha256(contract_file.read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        raise ContractValidationError(f"contract hash mismatch for {module_id}")


def _validate_uniqueness(modules: list[dict[str, str]]) -> None:
    module_ids = [item["module_id"] for item in modules]
    contract_paths = [item["contract_path"] for item in modules]
    if len(module_ids) != len(set(module_ids)):
        raise ContractValidationError("module_id_unique validation failed")
    if len(contract_paths) != len(set(contract_paths)):
        raise ContractValidationError("each module must reference a unique contract_path")


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_inputs(inputs, config, REQUIRED_INPUTS)
    leaked = find_forbidden_fields(inputs, forbidden_fields())
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    phase_ids, subphase_map = _parent_maps(
        inputs["validated_phase_registry"], inputs["validated_subphase_registry"]
    )
    registry, source_path = _load_registry(inputs["module_registry_yaml"])
    normalized = _validate_registry(registry, phase_ids, subphase_map, config)
    digest = stable_digest(normalized)
    policy = registry_baseline("module")
    artifact = {
        "artifact_id": f"validated-module-registry-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "source_path": source_path,
        "registry_id": policy["registry_id"],
        "module_count": len(normalized),
        "modules": normalized,
        "module_id_unique": True,
        "module_has_contract": True,
        "module_parent_valid": True,
        "contract_identity_valid": True,
        "contract_hash_valid": True,
        "registry_version_compatible": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }
    validate_output(
        artifact,
        schema_name="validated_module_registry.schema.yaml",
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


EXPECTED_REGISTRY_ID = str(registry_baseline("module")["registry_id"])
EXPECTED_MODULE_COUNT = int(registry_baseline("module")["module_count"])
