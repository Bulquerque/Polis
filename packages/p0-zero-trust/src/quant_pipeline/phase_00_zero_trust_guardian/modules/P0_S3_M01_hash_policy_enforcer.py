from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s3_artifacts import (
    artifact_record,
    artifact_records,
    entry_hash as _entry_hash,
    manifest_documents as _manifest_documents,
    mapping_or_path,
    validate_digest,
)
from ._p0_s3_shared import (
    CANONICAL_HASH_ALGORITHM,
    SHA256_RE,
    created_at,
    find_forbidden_fields,
    require_runtime_version,
    stable_digest,
    validate_output,
    workspace_root,
)

ALLOWED_ALGORITHM = CANONICAL_HASH_ALGORITHM
WORKSPACE_ROOT = workspace_root()


def _entry_path(record: dict[str, Any], base: Path, source: str) -> tuple[Path, str]:
    parsed = artifact_record(record, base, source)
    return parsed.resolved_path, parsed.path


def _hash_policy(value: Any) -> tuple[dict[str, Any], str]:
    policy, source = mapping_or_path(value, "hash_policy_yaml")
    leaked = find_forbidden_fields(policy, "hash_policy_yaml")
    if leaked:
        raise ContractValidationError(f"forbidden hash policy fields detected: {leaked}")
    algorithms = policy.get("allowed_algorithms")
    if algorithms is None:
        algorithms = [policy.get("algorithm")]
    if not isinstance(algorithms, list) or not all(isinstance(item, str) and item.strip() for item in algorithms):
        raise ContractValidationError("hash policy algorithms are malformed")
    normalized = {item.lower().replace("-", "") for item in algorithms}
    if CANONICAL_HASH_ALGORITHM not in normalized:
        raise ContractValidationError("hash policy does not allow SHA-256")
    fail_on = policy.get("fail_on")
    required_failures = {"missing_hash", "hash_mismatch"}
    if not isinstance(fail_on, list) or not required_failures.issubset(set(fail_on)):
        raise ContractValidationError("hash policy must fail on missing_hash and hash_mismatch")
    return policy, source


def _check(record, check_id: str) -> dict[str, Any]:
    code, actual_hash = validate_digest(record)
    passed = code == "PASS"
    return {
        "check_id": check_id,
        "manifest_source": record.source,
        "path": record.path,
        "algorithm": record.algorithm,
        "expected_hash": record.declared_hash,
        "actual_hash": actual_hash,
        "status": "PASS" if passed else "FAIL",
        "code": code,
        "severity": "NONE" if passed else "CRITICAL",
        "release_blocking": not passed,
    }


def _deduplicate(records) -> None:
    seen: set[str] = set()
    for record in records:
        if record.path in seen:
            raise ContractValidationError(f"duplicate artifact path in manifests: {record.path}")
        seen.add(record.path)


def _build_report(records, sources: list[str], policy_source: str, config: dict[str, Any]) -> dict[str, Any]:
    checks = [_check(record, f"HC-{index:06d}") for index, record in enumerate(records, 1)]
    counts = {
        code: sum(item["code"] == code for item in checks)
        for code in ("PASS", "MISSING_FILE", "MISSING_HASH", "HASH_MISMATCH", "DISALLOWED_ALGORITHM")
    }
    blocking = any(item["release_blocking"] for item in checks)
    normalized = {
        "policy_source": policy_source,
        "manifest_sources": sources,
        "checks": [
            {key: item[key] for key in ("manifest_source", "path", "algorithm", "expected_hash", "actual_hash", "code")}
            for item in checks
        ],
    }
    digest = stable_digest(normalized)
    return {
        "artifact_id": f"hash-integrity-report-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "policy_source": policy_source,
        "manifest_source_count": len(sources),
        "artifact_count": len(records),
        "passed_count": counts["PASS"],
        "missing_file_count": counts["MISSING_FILE"],
        "missing_hash_count": counts["MISSING_HASH"],
        "hash_mismatch_count": counts["HASH_MISMATCH"],
        "disallowed_algorithm_count": counts["DISALLOWED_ALGORITHM"],
        "checks": checks,
        "status": "FAIL" if blocking else "PASS",
        "severity": "CRITICAL" if blocking else "NONE",
        "release_blocking": blocking,
        "every_artifact_has_hash": all(SHA256_RE.fullmatch(record.declared_hash) is not None for record in records),
        "hash_algorithm_allowed": all(record.algorithm == CANONICAL_HASH_ALGORITHM for record in records),
        "all_digests_match": all(item["code"] == "PASS" for item in checks),
        "paths_internal": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    required_inputs = ["artifact_manifest_all_phases", "hash_policy_yaml"]
    missing = [name for name in required_inputs if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    require_runtime_version(config)
    _, policy_source = _hash_policy(inputs["hash_policy_yaml"])
    records, sources = artifact_records(inputs["artifact_manifest_all_phases"])
    if not records:
        raise ContractValidationError("artifact manifest collection is empty")
    _deduplicate(records)
    report = _build_report(records, sources, policy_source, config)
    validate_output(report, "hash_integrity_report.schema.yaml", "hash_integrity_report")
    return {
        "module_id": "P0.S3.M01",
        "module_name": "hash_policy_enforcer",
        "phase": "P0",
        "subphase": "P0.S3",
        "contract": "P0_S3_M01_hash_policy_enforcer.yaml",
        "required_inputs": required_inputs,
        "outputs": {"hash_integrity_report": report},
    }
