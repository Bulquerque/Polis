from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib

from ._module_executor import ContractValidationError
from ._s2_common import load_yaml_mapping, materialized_artifact, string_list
from ._s2_schema_compatibility import field_types, semantic_schema_gaps

def contract_map(value: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    registry = materialized_artifact(
        value,
        "contract_registry",
        {"lineage_id", "contract_count", "contracts", "global_contracts"},
    )
    contracts = registry["contracts"]
    declared_count = registry["contract_count"]
    if (
        not isinstance(declared_count, int)
        or not isinstance(contracts, list)
        or len(contracts) != declared_count
        or not all(isinstance(item, dict) for item in contracts)
    ):
        raise ContractValidationError(
            f"contract_registry must contain exactly {declared_count} contract mappings"
        )
    by_id: dict[str, dict[str, Any]] = {}
    for index, contract in enumerate(contracts):
        _validate_contract_entry(contract, index, by_id)
        by_id[contract["module_id"]] = contract
    global_contracts = registry["global_contracts"]
    if not isinstance(global_contracts, list) or not all(
        isinstance(item, dict) for item in global_contracts
    ):
        raise ContractValidationError("contract_registry.global_contracts must contain mappings")
    return by_id, global_contracts

def _validate_contract_entry(
    contract: dict[str, Any], index: int, existing: dict[str, dict[str, Any]]
) -> None:
    required = {
        "module_id",
        "module_name",
        "phase",
        "subphase",
        "inputs",
        "outputs",
        "consumes_from",
        "emits_to",
        "output_schemas",
    }
    missing = sorted(required.difference(contract))
    if missing:
        raise ContractValidationError(f"contract_registry contract {index} missing: {missing}")
    module_id = contract["module_id"]
    if not isinstance(module_id, str) or not module_id or module_id in existing:
        raise ContractValidationError(f"contract_registry has invalid/duplicate module_id: {module_id}")
    inputs = string_list(contract["inputs"], f"{module_id}.inputs")
    outputs = string_list(contract["outputs"], f"{module_id}.outputs")
    consumes = contract["consumes_from"]
    emits = contract["emits_to"]
    if not isinstance(consumes, dict) or not isinstance(emits, dict):
        raise ContractValidationError(f"{module_id} connections must be mappings")
    for field in ("modules", "artifacts", "phase_inputs"):
        string_list(consumes.get(field), f"{module_id}.consumes_from.{field}")
    for field in ("modules", "artifacts", "phase_outputs"):
        string_list(emits.get(field), f"{module_id}.emits_to.{field}")
    if inputs != consumes["artifacts"] or outputs != emits["artifacts"]:
        raise ContractValidationError(f"{module_id} contract IO differs from connection artifacts")
    if not isinstance(contract["output_schemas"], list):
        raise ContractValidationError(f"{module_id}.output_schemas must be a list")

def schema_map(
    value: Any,
    *,
    repository_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    registry = materialized_artifact(
        value,
        "schema_registry",
        {"lineage_id", "schemas", "mirrors", "authority_schema_count"},
    )
    schemas = registry["schemas"]
    mirrors = registry["mirrors"]
    if not isinstance(schemas, list) or not schemas or not all(isinstance(item, dict) for item in schemas):
        raise ContractValidationError("schema_registry.schemas must contain mappings")
    if registry["authority_schema_count"] != len(schemas):
        raise ContractValidationError("schema_registry authority_schema_count is malformed")
    if not isinstance(mirrors, list) or not all(isinstance(item, dict) for item in mirrors):
        raise ContractValidationError("schema_registry.mirrors must contain mappings")

    by_artifact: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(schemas):
        required = {"schema_id", "artifact_name", "path", "sha256", "required_fields", "structure_mode"}
        missing = sorted(required.difference(entry))
        if missing:
            raise ContractValidationError(f"schema_registry schema {index} missing: {missing}")
        artifact = entry["artifact_name"]
        if not isinstance(artifact, str) or not artifact or artifact in by_artifact:
            raise ContractValidationError(f"schema_registry has invalid/duplicate artifact_name: {artifact}")
        path = _internal_file(repository_root, entry["path"], f"authority schema path for {artifact}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise ContractValidationError(f"schema_registry authority hash mismatch: {artifact}")
        document = load_yaml_mapping(path, f"authority schema {artifact}")
        required_fields = string_list(entry["required_fields"], f"{artifact}.required_fields", allow_empty=False)
        declared_required = document.get("required_fields", document.get("required"))
        if required_fields != declared_required:
            raise ContractValidationError(f"schema_registry required fields mismatch: {artifact}")
        by_artifact[artifact] = {
            **entry,
            "field_types": field_types(document, required_fields),
            "document": document,
        }

    mirror_by_path: dict[str, dict[str, Any]] = {}
    for mirror in mirrors:
        path = mirror.get("path")
        if not isinstance(path, str) or path in mirror_by_path:
            raise ContractValidationError("schema_registry contains malformed/duplicate mirror path")
        if mirror.get("status") not in {"MATCH", "DIVERGED"}:
            raise ContractValidationError("schema_registry mirror status is malformed")
        mirror_by_path[path] = mirror
    return by_artifact, mirror_by_path

def matrix_rows(
    value: Any, contracts: dict[str, dict[str, Any]]
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    matrix = materialized_artifact(
        value,
        "validated_connection_matrix",
        {"lineage_id", "phase", "module_io_matrix", "connections", "module_count"},
    )
    rows = matrix["module_io_matrix"]
    connections = matrix["connections"]
    if not isinstance(rows, list) or not rows or not all(isinstance(item, dict) for item in rows):
        raise ContractValidationError("validated_connection_matrix.module_io_matrix is malformed")
    if matrix["module_count"] != len(rows):
        raise ContractValidationError("validated_connection_matrix.module_count is malformed")
    if not isinstance(connections, list) or not all(isinstance(item, dict) for item in connections):
        raise ContractValidationError("validated_connection_matrix.connections is malformed")
    for row in rows:
        if row.get("module_id") not in contracts:
            raise ContractValidationError(
                f"validated_connection_matrix references unknown module: {row.get('module_id')}"
            )
    return str(matrix["phase"]), rows, connections

def compatibility(
    contracts: dict[str, dict[str, Any]],
    global_contracts: list[dict[str, Any]],
    schemas: dict[str, dict[str, Any]],
    mirrors: dict[str, dict[str, Any]],
    matrix_phase: str,
    matrix_rows_value: list[dict[str, Any]],
    *,
    repository_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    io_checks, io_findings, input_schema_findings = _check_inputs(
        contracts, global_contracts, schemas, repository_root
    )
    schema_checks, schema_findings = _check_outputs(
        contracts, schemas, mirrors, repository_root
    )
    io_findings.extend(_check_matrix(contracts, matrix_phase, matrix_rows_value))
    schema_findings = input_schema_findings + schema_findings
    return io_checks, schema_checks, io_findings, schema_findings

def _check_inputs(
    contracts: dict[str, dict[str, Any]],
    global_contracts: list[dict[str, Any]],
    schemas: dict[str, dict[str, Any]],
    repository_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    optional, optional_producers = _optional_feedback(global_contracts, repository_root)
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    schema_findings: list[dict[str, Any]] = []
    for module_id, contract in contracts.items():
        dependencies = contract["consumes_from"]["modules"]
        phase_inputs = set(contract["consumes_from"]["phase_inputs"])
        for artifact in contract["inputs"]:
            optional_key = (contract["phase"], artifact)
            is_optional = optional_key in optional
            producers = [
                dependency
                for dependency in dependencies
                if dependency in contracts and artifact in contracts[dependency]["outputs"]
            ]
            source_kind = "optional_feedback" if is_optional else (
                "phase_input" if artifact in phase_inputs else "module_output"
            )
            producer = optional_producers.get(optional_key, "external_phase_input") if artifact in phase_inputs else (
                producers[0] if len(producers) == 1 else ""
            )
            status = "OPTIONAL" if is_optional else "COMPATIBLE"
            blocking = False
            message = "optional feedback absence does not block compatibility" if is_optional else "producer and consumer declarations are compatible"
            if artifact not in phase_inputs and len(producers) != 1 and module_id.startswith("P0."):
                status, blocking = "INCOMPATIBLE", True
                message = f"required artifact has {len(producers)} declared producers among dependencies"
                findings.append(finding("REQUIRED_ARTIFACT_PRODUCER_MISMATCH", "io", message, artifact, producer, module_id))
            if artifact not in schemas and not is_optional and source_kind == "module_output" and module_id.startswith("P0."):
                schema_findings.append(
                    finding(
                        "REQUIRED_ARTIFACT_SCHEMA_MISSING",
                        "schema",
                        "required artifact has no authoritative schema",
                        artifact,
                        producer,
                        module_id,
                    )
                )
            checks.append(
                {
                    "producer": producer,
                    "consumer": module_id,
                    "artifact": artifact,
                    "source_kind": source_kind,
                    "status": status,
                    "release_blocking": blocking,
                    "message": message,
                }
            )
    return checks, findings, schema_findings

def _check_outputs(
    contracts: dict[str, dict[str, Any]],
    schemas: dict[str, dict[str, Any]],
    mirrors: dict[str, dict[str, Any]],
    repository_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for module_id, contract in contracts.items():
        local_by_artifact = {
            item.get("artifact"): item
            for item in contract["output_schemas"]
            if isinstance(item, dict)
        }
        for artifact in contract["outputs"]:
            active_gate = module_id.startswith("P0.")
            authority = schemas.get(artifact)
            local = local_by_artifact.get(artifact)
            if authority is None or local is None:
                if active_gate:
                    findings.append(finding("OUTPUT_SCHEMA_BINDING_MISSING", "schema", "producer output is not bound to both local and authority schemas", artifact, module_id, ""))
                continue
            mirror = mirrors.get(local.get("schema_path"))
            mirror_status = mirror.get("status") if mirror else "MISSING"
            gaps: list[str] = []
            if mirror_status == "MATCH":
                local_path = _internal_file(repository_root, local["schema_path"], f"local schema for {artifact}")
                local_doc = load_yaml_mapping(local_path, f"local schema {artifact}")
                gaps = semantic_schema_gaps(authority["document"], local_doc)
            if (mirror_status != "MATCH" or gaps) and active_gate:
                message = f"local output schema mirror status is {mirror_status}"
                if gaps:
                    message += "; semantic gaps: " + "; ".join(gaps[:8])
                findings.append(finding("SCHEMA_SEMANTIC_INCOMPATIBILITY", "schema", message, artifact, module_id, ""))
            incompatible = active_gate and (mirror_status != "MATCH" or bool(gaps))
            checks.append(
                {
                    "producer": module_id,
                    "artifact": artifact,
                    "schema_id": authority["schema_id"],
                    "schema_path": authority["path"],
                    "schema_sha256": authority["sha256"],
                    "required_fields": authority["required_fields"],
                    "field_types": authority["field_types"],
                    "mirror_status": mirror_status,
                    "status": "INCOMPATIBLE" if incompatible else "COMPATIBLE",
                    "release_blocking": incompatible,
                }
            )
    return checks, findings

def _check_matrix(
    contracts: dict[str, dict[str, Any]], matrix_phase: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    by_id = {row.get("module_id"): row for row in rows}
    expected = {module_id for module_id in contracts if module_id.startswith(matrix_phase + ".")}
    if set(by_id) != expected:
        findings.append(finding("MATRIX_PHASE_COVERAGE_MISMATCH", "connection_matrix", "validated connection matrix does not cover exactly the phase contracts"))
    for module_id, row in by_id.items():
        contract = contracts[module_id]
        if row.get("consumes_from") != contract["consumes_from"] or row.get("emits_to") != contract["emits_to"]:
            findings.append(finding("MATRIX_CONTRACT_CONNECTION_MISMATCH", "connection_matrix", "validated matrix connection differs from contract registry", consumer=module_id))
    return findings

def _optional_feedback(
    global_contracts: list[dict[str, Any]], repository_root: Path
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], str]]:
    optional: set[tuple[str, str]] = set()
    producers: dict[tuple[str, str], str] = {}
    for item in global_contracts:
        path_value = item.get("contract_path")
        if not isinstance(path_value, str):
            raise ContractValidationError("global contract is missing contract_path")
        path = _internal_file(repository_root, path_value, "global contract path")
        document = load_yaml_mapping(path, f"global contract {path.name}")
        consumer = document.get("target_phase") or document.get("consumer_phase")
        producer = document.get("source_phase") or document.get("owner_phase") or document.get("producer_system")
        if isinstance(consumer, str) and isinstance(producer, str):
            for artifact in document.get("target_optional_feedback_inputs", []) or []:
                if isinstance(artifact, str) and artifact:
                    optional.add((consumer, artifact))
                    producers[(consumer, artifact)] = producer
    return optional, producers

def finding(
    code: str,
    scope: str,
    message: str,
    artifact: str = "",
    producer: str = "",
    consumer: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "CRITICAL",
        "scope": scope,
        "artifact": artifact,
        "producer": producer,
        "consumer": consumer,
        "message": message,
        "release_blocking": True,
    }

def _internal_file(repository_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{label} must be a repository-relative POSIX path")
    path = (repository_root / value).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} is outside repository: {value}") from exc
    if not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {value}")
    return path
