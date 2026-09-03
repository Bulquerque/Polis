from __future__ import annotations

import hashlib
import zipfile

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from . import _p0_s7_utils
from ._p0_s7_common import created_at, digest, envelope, load_mapping, reject_forbidden, validate_upstream
from ._p0_s7_package import inspect_package, validate_manifest, validate_required_files


def _resolve_package(value):
    from . import _p0_s7_common
    previous_root = _p0_s7_common.REPOSITORY_ROOT
    try:
        _p0_s7_common.REPOSITORY_ROOT = _p0_s7_utils.REPOSITORY_ROOT
        return _p0_s7_utils.internal_file(value, "agent_phase_package_zip")
    finally:
        _p0_s7_common.REPOSITORY_ROOT = previous_root


def _build_artifact(policy_path, policy_hash, package, package_path, entries, findings, manifest, config):
    blocking = [item for item in findings if item["severity"] == "blocking"]
    warnings = [item for item in findings if item["severity"] == "warning"]
    body = {
        "policy_source_path": policy_path, "policy_sha256": policy_hash,
        "package_path": package_path,
        "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "entries": sorted(entries, key=lambda item: item["path"]),
        "findings": findings, "agent_manifest_present": manifest is not None,
    }
    lineage = digest(body)
    return {
        "artifact_id": f"agent-package-validation-{lineage[:12]}",
        "created_at": created_at(config), "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{lineage}", **body,
        "entry_count": len(entries), "blocking_findings_count": len(blocking),
        "warning_findings_count": len(warnings), "package_structure_valid": not blocking,
        "no_cache_in_zip": not any(item["code"] == "cache_in_zip" for item in findings),
        "status": "BLOCKED" if blocking else "PASS", "blocking": bool(blocking),
        "release_blocking": bool(blocking), "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    required = ["agent_execution_policy", "agent_phase_package_zip"]
    if not isinstance(inputs, dict) or any(name not in inputs for name in required):
        raise ContractValidationError("missing required P0.S7.M04 inputs")
    config = config or {}
    reject_forbidden(inputs)
    policy, policy_path, policy_hash = load_mapping(inputs[required[0]], required[0])
    validate_upstream(policy, required[0])
    if policy.get("status") != "PASS" or policy.get("release_blocking") is True:
        raise ContractValidationError("agent execution policy is not PASS")
    package, package_path = _resolve_package(inputs[required[1]])
    if package.suffix.lower() != ".zip" or not zipfile.is_zipfile(package):
        raise ContractValidationError("agent package must be a valid ZIP")
    entries, findings, manifest = inspect_package(package, policy)
    findings.extend(validate_required_files(entries, policy.get("required_package_files", [])))
    findings.extend(validate_manifest(manifest, policy, entries))
    findings.sort(key=lambda item: (item["severity"], item["reason_code"], item["path"]))
    artifact = _build_artifact(
        policy_path, policy_hash, package, package_path, entries, findings, manifest, config
    )
    return envelope(
        "P0.S7.M04", "agent_package_validator",
        "P0_S7_M04_agent_package_validator.yaml", required,
        "agent_package_validation_report", artifact,
    )

