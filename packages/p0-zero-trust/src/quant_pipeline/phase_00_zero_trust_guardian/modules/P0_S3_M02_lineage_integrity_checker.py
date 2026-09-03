from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
import hashlib
import json

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s3_artifacts import artifact_records
from ._p0_s3_shared import (
    LINEAGE_RE,
    created_at,
    find_forbidden_fields,
    load_yaml_mapping,
    require_runtime_version,
    safe_repo_path,
    sha256_file,
    stable_digest,
    validate_output,
    validate_schema_value,
    workspace_root,
)
from ._module_executor import SCHEMA_ROOT
from ._p0_s3_lineage import runtime_lineage, strong_components


def _artifact(value: Any, name: str) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("outputs"), dict):
        value = value["outputs"].get(name)
    if not isinstance(value, dict):
        raise ContractValidationError(f"{name} must be an artifact mapping")
    return value


def _validate_upstream_artifact(artifact: dict[str, Any], name: str, schema_name: str) -> None:
    schema = load_yaml_mapping(SCHEMA_ROOT / schema_name, f"{name} schema")
    validate_schema_value(artifact, schema, name)
    lineage_id = artifact.get("lineage_id")
    if not isinstance(lineage_id, str) or LINEAGE_RE.fullmatch(lineage_id) is None:
        raise ContractValidationError(f"{name} has malformed lineage_id")
    leaked = find_forbidden_fields(artifact, name)
    if leaked:
        raise ContractValidationError(f"forbidden upstream fields detected: {leaked}")


def _legacy_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _validate_upstream_lineages(module_registry: dict[str, Any], contract_registry: dict[str, Any]) -> None:
    module_payload = module_registry["modules"]
    module_digests = {stable_digest(module_payload), _legacy_digest(module_payload)}
    if module_registry["lineage_id"] not in {f"sha256:{item}" for item in module_digests}:
        raise ContractValidationError("validated_module_registry lineage_id does not match its modules")
    contract_payload = {
        "contracts": contract_registry["contracts"],
        "global_contracts": contract_registry["global_contracts"],
    }
    contract_digests = {stable_digest(contract_payload), _legacy_digest(contract_payload)}
    if contract_registry["lineage_id"] not in {f"sha256:{item}" for item in contract_digests}:
        raise ContractValidationError("contract_registry lineage_id does not match its contents")


def _registry_maps(module_registry: dict[str, Any], contract_registry: dict[str, Any]):
    modules = module_registry.get("modules")
    contracts = contract_registry.get("contracts")
    if not isinstance(modules, list) or not modules or not all(isinstance(item, dict) for item in modules):
        raise ContractValidationError("validated_module_registry.modules is malformed")
    if not isinstance(contracts, list) or not contracts or not all(isinstance(item, dict) for item in contracts):
        raise ContractValidationError("contract_registry.contracts is malformed")
    module_ids = [item.get("module_id") for item in modules]
    contract_ids = [item.get("module_id") for item in contracts]
    if len(module_ids) != len(set(module_ids)):
        raise ContractValidationError("validated_module_registry contains duplicate module IDs")
    if len(contract_ids) != len(set(contract_ids)):
        raise ContractValidationError("contract_registry contains duplicate module IDs")
    module_by_id = {item["module_id"]: item for item in modules}
    contract_by_id = {item["module_id"]: item for item in contracts}
    if set(module_by_id) != set(contract_by_id):
        raise ContractValidationError("registry module identity sets do not match")
    return module_by_id, contract_by_id


def _manifest_index(records) -> tuple[dict[str, tuple[str, str]], list[str]]:
    indexed: dict[str, tuple[str, str]] = {}
    for record in records:
        if record.algorithm != "sha256" or len(record.declared_hash) != 64:
            raise ContractValidationError(f"manifest entry lacks a valid SHA-256: {record.path}")
        previous = indexed.get(record.path)
        current = (record.declared_hash, record.source)
        if previous is not None and previous != current:
            raise ContractValidationError(f"conflicting manifest provenance for {record.path}")
        indexed[record.path] = current
    return indexed, sorted({record.source for record in records})


def _check_structural_lineage(module_by_id, contract_by_id, manifest):
    producers: dict[str, list[str]] = {}
    for contract in contract_by_id.values():
        for output in contract["outputs"]:
            producers.setdefault(output, []).append(contract["module_id"])
    graph = {
        module_id: set(contract_by_id[module_id]["emits_to"]["modules"])
        for module_id in module_by_id
    }
    unknown = sorted({target for targets in graph.values() for target in targets if target not in graph})
    if unknown:
        raise ContractValidationError(f"contract graph references unknown modules: {unknown}")
    checks = []
    artifact_checks = []
    for module_id in sorted(module_by_id):
        module = module_by_id[module_id]
        contract = contract_by_id[module_id]
        checks.append(_check_module(module_id, module, contract, contract_by_id, graph, manifest, producers, artifact_checks))
    return checks, artifact_checks, strong_components(graph)


def _check_module(module_id, module, contract, contract_by_id, graph, manifest, producers, artifact_checks):
    root = workspace_root()
    path, relative = safe_repo_path(module["contract_path"], root, f"{module_id}.contract_path")
    if not path.is_file():
        raise ContractValidationError(f"module contract does not exist: {relative}")
    actual_hash = sha256_file(path)
    manifest_hash, manifest_source = manifest.get(relative, ("", ""))
    codes: list[str] = []
    expected_phase = module_id.split(".", 1)[0]
    expected_subphase = module_id.rsplit(".M", 1)[0]
    if contract["contract_id"] != module_id:
        codes.append("CONTRACT_ID_MISMATCH")
    if contract["contract_path"] != relative:
        codes.append("CONTRACT_PATH_MISMATCH")
    if contract["contract_sha256"] != module["contract_sha256"]:
        codes.append("REGISTRY_HASH_DISAGREEMENT")
    if actual_hash not in {module["contract_sha256"], contract["contract_sha256"]}:
        codes.append("CONTRACT_HASH_MISMATCH")
    if not manifest_source:
        codes.append("MISSING_MANIFEST_PROVENANCE")
    elif manifest_hash != actual_hash:
        codes.append("MANIFEST_HASH_MISMATCH")
    if module.get("phase_id") != expected_phase or contract.get("subphase") != expected_subphase:
        codes.append("PARENT_ID_MISMATCH")
    if module_id in contract["consumes_from"]["modules"] or module_id in contract["emits_to"]["modules"]:
        codes.append("SELF_PARENT_CYCLE")
    for parent in contract["consumes_from"]["modules"]:
        if module_id not in graph[parent]:
            codes.append("NONRECIPROCAL_PARENT")
    for child in contract["emits_to"]["modules"]:
        if module_id not in contract_by_id[child]["consumes_from"]["modules"]:
            codes.append("NONRECIPROCAL_CHILD")
    declared_inputs = set(contract["consumes_from"]["artifacts"]) | set(contract["consumes_from"]["phase_inputs"])
    if set(contract["inputs"]) != declared_inputs:
        codes.append("INPUT_PARENT_MISMATCH")
    if set(contract["outputs"]) != set(contract["emits_to"]["artifacts"]):
        codes.append("OUTPUT_LINEAGE_MISMATCH")
    _check_output_schemas(module_id, contract, producers, artifact_checks, codes)
    codes = sorted(set(codes))
    return {
        "module_id": module_id,
        "contract_path": relative,
        "contract_sha256": actual_hash,
        "manifest_source": manifest_source,
        "parent_module_count": len(contract["consumes_from"]["modules"]),
        "input_count": len(contract["inputs"]),
        "output_count": len(contract["outputs"]),
        "schema_count": len(contract["output_schemas"]),
        "status": "FAIL" if codes else "PASS",
        "codes": codes or ["PASS"],
    }


def _check_output_schemas(module_id, contract, producers, artifact_checks, module_codes):
    schema_by_artifact = {item["artifact"]: item for item in contract["output_schemas"]}
    if set(schema_by_artifact) != set(contract["outputs"]):
        module_codes.append("OUTPUT_SCHEMA_COVERAGE_MISMATCH")
    root = workspace_root()
    for artifact in contract["outputs"]:
        codes: list[str] = []
        schema_record = schema_by_artifact.get(artifact)
        schema_path_text = ""
        if schema_record is None:
            codes.append("MISSING_SCHEMA_PROVENANCE")
        else:
            schema_path, schema_path_text = safe_repo_path(
                schema_record["schema_path"], root, f"{module_id}.{artifact}.schema_path"
            )
            if not schema_path.is_file():
                codes.append("MISSING_SCHEMA")
            elif sha256_file(schema_path) != schema_record["schema_sha256"]:
                codes.append("SCHEMA_HASH_MISMATCH")
        artifact_checks.append(
            {
                "artifact": artifact,
                "producer": module_id,
                "producer_count": len(producers.get(artifact, [])),
                "schema_path": schema_path_text,
                "status": "FAIL" if codes else "PASS",
                "codes": codes or ["PASS"],
            }
        )
        module_codes.extend(codes)


def _prepare_inputs(inputs: dict, config: dict[str, Any]):
    required = ["artifact_manifest_all_phases", "validated_module_registry", "contract_registry"]
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    require_runtime_version(config)
    modules = _artifact(inputs["validated_module_registry"], "validated_module_registry")
    contracts = _artifact(inputs["contract_registry"], "contract_registry")
    _validate_upstream_artifact(modules, "validated_module_registry", "validated_module_registry.schema.yaml")
    _validate_upstream_artifact(contracts, "contract_registry", "contract_registry.schema.yaml")
    records, manifest_sources = artifact_records(inputs["artifact_manifest_all_phases"])
    manifest, _ = _manifest_index(records)
    _validate_upstream_lineages(modules, contracts)
    module_by_id, contract_by_id = _registry_maps(modules, contracts)
    return required, modules, contracts, records, manifest_sources, manifest, module_by_id, contract_by_id


def _build_report(modules, contracts, records, sources, module_by_id, checks, artifact_checks, cycles, runtime_checks, runtime_cycles, runtime_available, config):
    failed_modules = sum(item["status"] == "FAIL" for item in checks)
    failed_artifacts = sum(item["status"] == "FAIL" for item in artifact_checks)
    failed_runtime = sum(item["status"] == "FAIL" for item in runtime_checks)
    blocking = bool(failed_modules or failed_artifacts or failed_runtime or cycles)
    normalized = {
        "module_registry": modules["lineage_id"], "contract_registry": contracts["lineage_id"],
        "manifest_sources": sources, "checks": checks, "artifact_checks": artifact_checks,
        "declared_cycles": cycles, "runtime_artifact_checks": runtime_checks, "runtime_cycles": runtime_cycles,
    }
    digest = stable_digest(normalized)
    return {
        "artifact_id": f"lineage-integrity-report-{digest[:12]}", "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION, "lineage_id": f"sha256:{digest}",
        "validated_module_registry_lineage_id": modules["lineage_id"],
        "contract_registry_lineage_id": contracts["lineage_id"], "manifest_sources": sources,
        "expected_module_count": len(module_by_id), "module_count": len(checks), "artifact_count": len(artifact_checks),
        "passed_module_count": len(checks)-failed_modules, "failed_module_count": failed_modules,
        "passed_artifact_count": len(artifact_checks)-failed_artifacts, "failed_artifact_count": failed_artifacts,
        "declared_cycle_count": len(cycles), "declared_cycles": cycles,
        "runtime_lineage_available": runtime_available, "runtime_lineage_record_count": len(runtime_checks),
        "runtime_lineage_failure_count": failed_runtime, "runtime_artifact_checks": runtime_checks,
        "runtime_cycle_count": len(runtime_cycles), "runtime_cycles": runtime_cycles, "checks": checks,
        "artifact_checks": artifact_checks, "lineage_id_present": True,
        "output_points_to_producer": failed_artifacts == 0 and failed_runtime == 0,
        "contract_hashes_match": all("CONTRACT_HASH_MISMATCH" not in item["codes"] for item in checks),
        "manifest_provenance_complete": all(not ({"MISSING_MANIFEST_PROVENANCE","MANIFEST_HASH_MISMATCH"}&set(item["codes"])) for item in checks),
        "parent_links_valid": all(not ({"PARENT_ID_MISMATCH","NONRECIPROCAL_PARENT","NONRECIPROCAL_CHILD","SELF_PARENT_CYCLE","INPUT_PARENT_MISMATCH"}&set(item["codes"])) for item in checks) and failed_runtime == 0,
        "status": "FAIL" if blocking else "PASS", "severity": "CRITICAL" if blocking else "NONE",
        "release_blocking": blocking, "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    prepared = _prepare_inputs(inputs, config)
    required, modules, contracts, records, sources, manifest, module_by_id, contract_by_id = prepared
    checks, artifact_checks, cycles = _check_structural_lineage(module_by_id, contract_by_id, manifest)
    runtime_checks, runtime_cycles, runtime_available = runtime_lineage(records, set(module_by_id))
    report = _build_report(modules, contracts, records, sources, module_by_id, checks, artifact_checks, cycles, runtime_checks, runtime_cycles, runtime_available, config)
    validate_output(report, "lineage_integrity_report.schema.yaml", "lineage_integrity_report")
    return {
        "module_id": "P0.S3.M02", "module_name": "lineage_integrity_checker", "phase": "P0",
        "subphase": "P0.S3", "contract": "P0_S3_M02_lineage_integrity_checker.yaml",
        "required_inputs": required, "outputs": {"lineage_integrity_report": report},
    }
