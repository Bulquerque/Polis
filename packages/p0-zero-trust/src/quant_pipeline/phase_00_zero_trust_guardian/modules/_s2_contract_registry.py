from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import hashlib
import re

from ._module_executor import ContractValidationError
from ._s2_common import load_yaml_mapping_malformed, string_list


MODULE_ID_PATTERN = re.compile(
    r"^P(?P<phase>[0-9]+)\.S(?P<subphase>[0-9]+)\.M(?P<module>[0-9]+)$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def validate_module_contracts(
    manifest: dict[str, Any],
    *,
    repository_root: Path,
    resolve_internal_path: Callable[[Any, str], tuple[Path, str]],
    schema_for_output: Callable[[Path, str], Path],
    expected_registry_id: str,
) -> list[dict[str, Any]]:
    entries = _validate_manifest_header(manifest, expected_registry_id)
    _validate_manifest_uniqueness(entries)
    loaded = _load_contract_documents(entries, resolve_internal_path)
    normalized = _normalize_contracts(
        loaded,
        repository_root=repository_root,
        schema_for_output=schema_for_output,
    )
    _validate_bidirectional_connections(normalized)
    return normalized


def _validate_manifest_header(
    manifest: dict[str, Any], expected_registry_id: str
) -> list[dict[str, Any]]:
    if manifest.get("registry_id") != expected_registry_id:
        raise ContractValidationError("contracts_all_phases registry_id is incompatible")
    if manifest.get("hash_algorithm") != "sha256":
        raise ContractValidationError("contracts_all_phases hash_algorithm must be sha256")

    declared_count = manifest.get("module_count")
    if not isinstance(declared_count, int) or declared_count <= 0:
        raise ContractValidationError("contracts_all_phases module_count must be a positive integer")
    entries = manifest.get("modules")
    if not isinstance(entries, list) or len(entries) != declared_count:
        raise ContractValidationError(
            f"contracts_all_phases must contain exactly {declared_count} entries"
        )
    if not all(isinstance(entry, dict) for entry in entries):
        raise ContractValidationError("contracts_all_phases modules must be mappings")
    return entries


def _validate_manifest_uniqueness(entries: list[dict[str, Any]]) -> None:
    module_ids = [entry.get("module_id") for entry in entries]
    paths = [entry.get("contract_path") for entry in entries]
    hashes = [entry.get("contract_sha256") for entry in entries]
    if not all(isinstance(value, str) and value for value in module_ids):
        raise ContractValidationError("contracts_all_phases contains malformed module_id")
    if len(module_ids) != len(set(module_ids)):
        raise ContractValidationError("contract IDs must be unique")
    if not all(isinstance(value, str) and value for value in paths) or len(paths) != len(set(paths)):
        raise ContractValidationError("contract paths must be present and unique")
    if not all(isinstance(value, str) and SHA256_PATTERN.fullmatch(value) for value in hashes):
        raise ContractValidationError("contract hashes must be valid sha256 values")
    if len(hashes) != len(set(hashes)):
        raise ContractValidationError("contract hashes must be unique")


def _load_contract_documents(
    entries: list[dict[str, Any]],
    resolve_internal_path: Callable[[Any, str], tuple[Path, str]],
) -> dict[str, tuple[Path, dict[str, Any], dict[str, Any]]]:
    loaded: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]] = {}
    for entry in entries:
        module_id = entry["module_id"]
        if MODULE_ID_PATTERN.fullmatch(module_id) is None:
            raise ContractValidationError(f"invalid module contract ID: {module_id}")
        contract_file, canonical_path = resolve_internal_path(
            entry["contract_path"], f"contract_path for {module_id}"
        )
        if contract_file.parent.name != "modules" or contract_file.suffix != ".yaml":
            raise ContractValidationError(
                f"contract_path is not an internal module contract: {canonical_path}"
            )
        if not contract_file.is_file():
            raise ContractValidationError(f"module contract does not exist: {canonical_path}")
        actual_hash = hashlib.sha256(contract_file.read_bytes()).hexdigest()
        if actual_hash != entry["contract_sha256"]:
            raise ContractValidationError(f"module contract hash mismatch: {module_id}")
        contract = load_yaml_mapping_malformed(contract_file, f"module contract {module_id}")
        expected_filename = f"{module_id.replace('.', '_')}_{entry.get('module_name')}.yaml"
        if contract_file.name != expected_filename:
            raise ContractValidationError(f"module contract filename identity mismatch: {module_id}")
        if (
            contract.get("module_id") != module_id
            or contract.get("module_name") != entry.get("module_name")
            or contract.get("subphase") != entry.get("subphase_id")
        ):
            raise ContractValidationError(f"module contract YAML identity mismatch: {module_id}")
        loaded[module_id] = (contract_file, contract, entry)
    return loaded


def _normalize_contracts(
    loaded: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]],
    *,
    repository_root: Path,
    schema_for_output: Callable[[Path, str], Path],
) -> list[dict[str, Any]]:
    known_modules = set(loaded)
    normalized: list[dict[str, Any]] = []
    for module_id in sorted(loaded, key=_module_sort_key):
        contract_file, contract, entry = loaded[module_id]
        inputs = string_list(contract.get("inputs"), f"{module_id} inputs")
        outputs = string_list(contract.get("outputs"), f"{module_id} outputs")
        consumes, emits = _validated_connections(contract, module_id)
        if inputs != consumes["artifacts"] or outputs != emits["artifacts"]:
            raise ContractValidationError(
                f"{module_id} connection artifacts do not match contract IO"
            )
        unknown = sorted((set(consumes["modules"]) | set(emits["modules"])) - known_modules)
        if unknown:
            raise ContractValidationError(
                f"{module_id} connections reference unknown modules: {unknown}"
            )
        output_schemas = _bind_output_schemas(
            contract_file,
            outputs,
            module_id,
            repository_root=repository_root,
            schema_for_output=schema_for_output,
        )
        normalized.append(
            {
                "contract_id": module_id,
                "module_id": module_id,
                "module_name": contract["module_name"],
                "phase": str(contract.get("phase")),
                "subphase": contract["subphase"],
                "contract_path": entry["contract_path"],
                "contract_sha256": entry["contract_sha256"],
                "inputs": inputs,
                "outputs": outputs,
                "consumes_from": consumes,
                "emits_to": emits,
                "output_schemas": output_schemas,
            }
        )
    return normalized


def _validated_connections(
    contract: dict[str, Any], module_id: str
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    allowed = contract.get("allowed_connections")
    # P4 V14.9 module contracts predate the RC4 connection block. Their
    # inputs/outputs are the authoritative artifact contract and module edges
    # are intentionally absent; normalize them into the active representation.
    if allowed is None and module_id.startswith("P4."):
        return (
            {"modules": [], "artifacts": string_list(contract.get("inputs"), f"{module_id} inputs"), "phase_inputs": []},
            {"modules": [], "artifacts": string_list(contract.get("outputs"), f"{module_id} outputs"), "phase_outputs": []},
        )
    if not isinstance(allowed, dict):
        raise ContractValidationError(f"{module_id} has no allowed_connections mapping")
    consumes = allowed.get("consumes_from")
    emits = allowed.get("emits_to")
    if not isinstance(consumes, dict) or not isinstance(emits, dict):
        raise ContractValidationError(f"{module_id} must declare source and target connections")
    return (
        {
            "modules": string_list(consumes.get("modules"), f"{module_id} source modules"),
            "artifacts": string_list(consumes.get("artifacts"), f"{module_id} source artifacts"),
            "phase_inputs": string_list(consumes.get("phase_inputs"), f"{module_id} phase_inputs"),
        },
        {
            "modules": string_list(emits.get("modules"), f"{module_id} target modules"),
            "artifacts": string_list(emits.get("artifacts"), f"{module_id} target artifacts"),
            "phase_outputs": string_list(emits.get("phase_outputs"), f"{module_id} phase_outputs"),
        },
    )


def _bind_output_schemas(
    contract_file: Path,
    outputs: list[str],
    module_id: str,
    *,
    repository_root: Path,
    schema_for_output: Callable[[Path, str], Path],
) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    for artifact in outputs:
        schema_path = schema_for_output(contract_file, artifact)
        if not schema_path.is_file():
            raise ContractValidationError(f"missing output schema for {module_id}: {artifact}")
        schema = load_yaml_mapping_malformed(schema_path, f"schema for {module_id}.{artifact}")
        declared_name = schema.get("artifact_name")
        if declared_name is not None and declared_name != artifact:
            raise ContractValidationError(
                f"output schema identity mismatch for {module_id}: {artifact}"
            )
        bindings.append(
            {
                "artifact": artifact,
                "schema_path": schema_path.relative_to(repository_root).as_posix(),
                "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
            }
        )
    return bindings


def _validate_bidirectional_connections(contracts: list[dict[str, Any]]) -> None:
    by_id = {item["module_id"]: item for item in contracts}
    for item in contracts:
        for target in item["emits_to"]["modules"]:
            if item["module_id"] not in by_id[target]["consumes_from"]["modules"]:
                raise ContractValidationError(
                    f"connection is not bidirectional: {item['module_id']} -> {target}"
                )


def validate_global_contracts(
    paths: list[Path], *, repository_root: Path, global_schema_root: Path
) -> list[dict[str, Any]]:
    normalized = [
        _normalize_global_contract(
            path,
            repository_root=repository_root,
            global_schema_root=global_schema_root,
        )
        for path in paths
    ]
    ids = [item["contract_id"] for item in normalized]
    hashes = [item["contract_sha256"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ContractValidationError("global contract IDs must be unique")
    if len(hashes) != len(set(hashes)):
        raise ContractValidationError("global contract hashes must be unique")
    return normalized


def _normalize_global_contract(
    path: Path, *, repository_root: Path, global_schema_root: Path
) -> dict[str, Any]:
    contract = load_yaml_mapping_malformed(path, f"global contract {path.name}")
    contract_id = contract.get("contract_id") or path.stem
    source = contract.get("source_phase") or contract.get("owner_phase") or contract.get("producer_system")
    target = contract.get("target_phase") or contract.get("consumer_phase")
    if not isinstance(contract_id, str) or not contract_id:
        raise ContractValidationError(f"global contract has no ID: {path.name}")
    if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
        raise ContractValidationError(f"global contract has no source/target: {path.name}")
    artifacts = _global_artifacts(contract, path.name)
    schemas = _global_schema_bindings(
        artifacts,
        path.name,
        repository_root=repository_root,
        global_schema_root=global_schema_root,
    )
    return {
        "contract_id": contract_id,
        "contract_path": path.relative_to(repository_root).as_posix(),
        "contract_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "producer": source,
        "consumer": target,
        "artifacts": artifacts,
        "schemas": schemas,
    }


def _global_artifacts(contract: dict[str, Any], filename: str) -> list[str]:
    artifacts = contract.get("shared_artifacts")
    connections = contract.get("artifacts")
    if artifacts is None and isinstance(connections, list):
        artifacts = [item.get("artifact") if isinstance(item, dict) else None for item in connections]
        if not all(
            isinstance(item, dict) and item.get("producer") and item.get("consumer")
            for item in connections
        ):
            raise ContractValidationError(f"global artifact connection is malformed: {filename}")
    artifacts = string_list(artifacts, f"{filename} shared artifacts")
    if not artifacts:
        raise ContractValidationError(f"global contract has no shared connection artifacts: {filename}")
    if contract.get("channel_type") is None and connections is None:
        outputs = set(string_list(contract.get("source_outputs"), f"{filename} source_outputs"))
        required = string_list(contract.get("target_required_inputs"), f"{filename} target_required_inputs")
        optional = string_list(
            contract.get("target_optional_feedback_inputs"),
            f"{filename} target_optional_feedback_inputs",
        )
        if outputs != set(artifacts) or set(required) | set(optional) != set(artifacts):
            raise ContractValidationError(
                f"global source/target artifacts are inconsistent: {filename}"
            )
    return artifacts


def _global_schema_bindings(
    artifacts: list[str],
    filename: str,
    *,
    repository_root: Path,
    global_schema_root: Path,
) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    for artifact in artifacts:
        path = global_schema_root / f"{artifact}.schema.yaml"
        if not path.is_file():
            raise ContractValidationError(f"missing global schema for {filename}: {artifact}")
        load_yaml_mapping_malformed(path, f"global schema {artifact}")
        bindings.append(
            {
                "artifact": artifact,
                "schema_path": path.relative_to(repository_root).as_posix(),
                "schema_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return bindings


def _module_sort_key(module_id: str) -> tuple[int, ...]:
    return tuple(int(part[1:]) for part in module_id.split("."))
