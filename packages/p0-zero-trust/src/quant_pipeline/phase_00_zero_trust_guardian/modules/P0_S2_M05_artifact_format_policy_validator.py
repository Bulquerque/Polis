from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import re

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ._s2_artifact_formats import (
    actual_format,
    artifact_sha256,
    forbidden_format_findings,
    inspect_content,
    load_mapping_input,
    resolve_internal_path,
    finding,
    validate_policy,
)
from ._s2_common import (
    created_at,
    find_forbidden_fields,
    load_yaml_mapping,
    stable_digest,
    validate_schema_value,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    return load_yaml_mapping(path, label)


def _find_forbidden_fields(value: Any, path: str = "inputs") -> list[str]:
    return find_forbidden_fields(value, path)



def _resolve_internal_path(
    value: Any, label: str, *, must_exist: bool = True
) -> tuple[Path, str]:
    return resolve_internal_path(
        value, label, repository_root=REPOSITORY_ROOT, must_exist=must_exist
    )


def _finding(
    artifact_id: str,
    path: str,
    code: str,
    message: str,
    expected_format: str,
    actual_format_value: str,
) -> dict[str, str]:
    return finding(
        artifact_id, path, code, message, expected_format, actual_format_value
    )

def _load_policy(value: Any) -> tuple[dict[str, Any], str]:
    policy, source = load_mapping_input(
        value,
        "forbidden",
        "artifact_format_policy_yaml",
        repository_root=REPOSITORY_ROOT,
        load_yaml=_load_yaml_mapping,
    )
    formats, forbidden = validate_policy(policy)
    return {**policy, "formats": formats, "forbidden": forbidden}, source


def _load_registry(value: Any) -> tuple[dict[str, Any], str]:
    registry, source = load_mapping_input(
        value,
        "artifacts",
        "artifact_registry",
        repository_root=REPOSITORY_ROOT,
        load_yaml=_load_yaml_mapping,
    )
    artifacts = registry.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ContractValidationError("artifact_registry artifacts must be non-empty")
    return registry, source


def _actual_format(path: Path) -> str:
    return actual_format(path)


def _content_error(path: Path, expected_format: str) -> str | None:
    return inspect_content(path, expected_format)


def _validate_artifacts(
    registry: dict[str, Any],
    formats: dict[str, str],
    forbidden_rules: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    artifacts = registry["artifacts"]
    if registry.get("inventory_scope") != "all_phase_artifacts":
        raise ContractValidationError("artifact_registry inventory_scope must be all_phase_artifacts")
    if registry.get("inventory_complete") is not True:
        raise ContractValidationError("artifact_registry must declare inventory_complete: true")
    if registry.get("expected_artifact_count") != len(artifacts):
        raise ContractValidationError("artifact_registry expected_artifact_count is inconsistent")

    normalized: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    ids: list[str] = []
    paths: list[str] = []
    for index, item in enumerate(artifacts):
        record, entry_findings = _validate_artifact_entry(
            item,
            index,
            formats,
            forbidden_rules or [],
        )
        ids.append(record["artifact_id"])
        paths.append(record["path"])
        normalized.append(record)
        findings.extend(entry_findings)
    if len(ids) != len(set(ids)):
        raise ContractValidationError("artifact_registry artifact_id values must be unique")
    if len(paths) != len(set(paths)):
        raise ContractValidationError("artifact_registry paths must be unique")
    return normalized, findings


def _validate_artifact_entry(
    item: Any,
    index: int,
    formats: dict[str, str],
    forbidden_rules: list[str],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not isinstance(item, dict):
        raise ContractValidationError(f"artifact_registry entry {index} must be a mapping")
    required = {"artifact_id", "artifact_type", "format", "path"}
    missing = sorted(required.difference(item))
    if missing:
        raise ContractValidationError(f"artifact_registry entry {index} missing fields: {missing}")
    extra = sorted(set(item).difference(required | {"sha256"}))
    if extra:
        raise ContractValidationError(f"artifact_registry entry {index} has extra fields: {extra}")
    artifact_id, artifact_type, declared_format = (
        item["artifact_id"], item["artifact_type"], item["format"]
    )
    if not all(isinstance(value, str) and value for value in (artifact_id, artifact_type, declared_format)):
        raise ContractValidationError(f"artifact_registry entry {index} has malformed identity")
    path, canonical_path = _resolve_internal_path(item["path"], f"artifact path for {artifact_id}")
    expected_format = formats.get(artifact_type, "")
    observed_format = _actual_format(path)
    entry_findings = _format_findings(
        artifact_id,
        artifact_type,
        declared_format,
        expected_format,
        observed_format,
        canonical_path,
        path,
        forbidden_rules,
    )
    actual_hash = artifact_sha256(path)
    entry_findings.extend(
        _declared_hash_findings(
            item.get("sha256"),
            actual_hash,
            artifact_id,
            canonical_path,
            expected_format or declared_format,
            observed_format,
        )
    )
    return (
        {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "declared_format": declared_format,
            "expected_format": expected_format,
            "actual_format": observed_format,
            "path": canonical_path,
            "sha256": actual_hash,
            "status": "BLOCKED" if entry_findings else "PASS",
        },
        entry_findings,
    )



def _declared_hash_findings(
    declared_hash: Any,
    actual_hash: str,
    artifact_id: str,
    canonical_path: str,
    expected_format: str,
    observed_format: str,
) -> list[dict[str, str]]:
    if declared_hash is None:
        return []
    if not isinstance(declared_hash, str) or SHA256_PATTERN.fullmatch(declared_hash) is None:
        raise ContractValidationError(f"invalid sha256 declaration for {artifact_id}")
    if declared_hash == actual_hash:
        return []
    return [
        _finding(
            artifact_id,
            canonical_path,
            "content_hash_mismatch",
            "declared sha256 does not match artifact bytes; S3 remains the hash-policy authority",
            expected_format,
            observed_format,
        )
    ]

def _format_findings(
    artifact_id: str,
    artifact_type: str,
    declared_format: str,
    expected_format: str,
    observed_format: str,
    canonical_path: str,
    path: Path,
    forbidden_rules: list[str],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not expected_format:
        findings.append(_finding(artifact_id, canonical_path, "artifact_type_not_allowlisted", f"artifact_type {artifact_type!r} is not present in policy formats", "allowlisted artifact type", observed_format))
    elif declared_format != expected_format:
        findings.append(_finding(artifact_id, canonical_path, "declared_format_mismatch", f"declared format {declared_format!r} differs from policy", expected_format, observed_format))
    if expected_format and observed_format != expected_format:
        findings.append(_finding(artifact_id, canonical_path, "extension_mismatch", "artifact extension does not match policy format", expected_format, observed_format))
    parts = set(PurePosixPath(canonical_path).parts)
    if artifact_type == "contract" and (expected_format != "yaml" or observed_format != "yaml"):
        findings.append(_finding(artifact_id, canonical_path, "contract_not_yaml", "contracts are permitted only as .yaml mappings", "yaml", observed_format))
    if ("contracts" in parts or "modules" in parts) and artifact_type != "contract":
        findings.append(_finding(artifact_id, canonical_path, "contract_path_misclassified", "files in contracts/modules must be classified as contract", "yaml", observed_format))
    if expected_format:
        error = _content_error(path, expected_format)
        if error:
            findings.append(_finding(artifact_id, canonical_path, "content_format_mismatch", error, expected_format, observed_format))
    findings.extend(
        forbidden_format_findings(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=canonical_path,
            actual=observed_format,
            rules=forbidden_rules,
            finding_factory=_finding,
        )
    )
    return findings


def run_module(inputs: dict, config: dict | None = None) -> dict:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    required_inputs = ["artifact_registry", "artifact_format_policy_yaml"]
    missing = [name for name in required_inputs if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = _find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")

    registry, registry_source = _load_registry(inputs["artifact_registry"])
    policy, policy_source = _load_policy(inputs["artifact_format_policy_yaml"])
    checked, findings = _validate_artifacts(registry, policy["formats"], policy["forbidden"])
    digest = stable_digest(
        {
            "policy_id": policy["policy_id"],
            "checked_artifacts": checked,
            "findings": findings,
        }
    )
    artifact = _build_report(
        checked,
        findings,
        policy,
        registry_source,
        policy_source,
        digest,
        config,
    )
    schema = _load_yaml_mapping(
        SCHEMA_ROOT / "artifact_format_validation_report.schema.yaml",
        "artifact format validation report schema",
    )
    validate_schema_value(artifact, schema, "artifact_format_validation_report")
    leaked_output = _find_forbidden_fields(artifact, "artifact_format_validation_report")
    if leaked_output:
        raise ContractValidationError(f"forbidden output fields detected: {leaked_output}")
    return {
        "module_id": "P0.S2.M05",
        "module_name": "artifact_format_policy_validator",
        "phase": "P0",
        "subphase": "P0.S2",
        "contract": "P0_S2_M05_artifact_format_policy_validator.yaml",
        "required_inputs": required_inputs,
        "outputs": {"artifact_format_validation_report": artifact},
    }


def _build_report(
    checked: list[dict[str, Any]],
    findings: list[dict[str, str]],
    policy: dict[str, Any],
    registry_source: str,
    policy_source: str,
    digest: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    format_allowed = not findings
    contracts_in_yaml = not any(
        item["code"] in {"contract_not_yaml", "contract_path_misclassified"}
        for item in findings
    )
    return {
        "artifact_id": f"artifact-format-validation-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "registry_source_path": registry_source,
        "policy_source_path": policy_source,
        "policy_id": policy["policy_id"],
        "artifact_count": len(checked),
        "checked_artifacts": checked,
        "findings": findings,
        "blocking_findings_count": len(findings),
        "status": "BLOCKED" if findings else "PASS",
        "blocking": bool(findings),
        "format_allowed": format_allowed,
        "contracts_in_yaml": contracts_in_yaml,
        "policy_non_empty": True,
        "paths_internal": True,
        "validation_evidence_status": (
            "domain_oracle_failed"
            if findings
            else "domain_oracle_pass_pending_independent_judge"
        ),
        "promotion_blocked": True,
    }
