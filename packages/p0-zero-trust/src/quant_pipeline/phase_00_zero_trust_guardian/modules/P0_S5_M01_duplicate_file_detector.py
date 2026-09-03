from __future__ import annotations

from collections import defaultdict
from typing import Any

from ._module_executor import ContractValidationError
from ._s5_core import (
    envelope,
    find_forbidden_fields,
    module_result,
    normalize_repo_path,
    require_config,
)
from ._s5_duplication import classify_duplicate
from ._s5_schema import validate_artifact


def _entries(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        entries = value
    elif isinstance(value, dict):
        entries = value.get("files", value.get("entries"))
    else:
        entries = None
    if not isinstance(entries, list) or not entries:
        raise ContractValidationError(f"{label} must contain a non-empty materialized file list")
    if not all(isinstance(item, dict) for item in entries):
        raise ContractValidationError(f"{label} entries must be mappings")
    return entries


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ContractValidationError(f"{label} sha256 is malformed")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ContractValidationError(f"{label} sha256 is malformed") from exc
    return value.lower()


def _index(entries: list[dict[str, Any]], label: str, require_hash: bool) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        path = normalize_repo_path(entry.get("path"), f"{label}[{index}]")
        if path in result:
            raise ContractValidationError(f"{label} contains duplicate path: {path}")
        if require_hash:
            _sha(entry.get("sha256"), f"{label}[{index}]")
        size = entry.get("size_bytes")
        if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
            raise ContractValidationError(f"{label}[{index}] size_bytes is malformed")
        result[path] = entry
    return result


def _allowlisted_groups(config: dict[str, Any]) -> set[tuple[str, ...]]:
    groups = config.get("allowlisted_duplicate_groups", [])
    if not isinstance(groups, list) or not all(
        isinstance(group, list) and len(group) > 1 and all(isinstance(path, str) for path in group)
        for group in groups
    ):
        raise ContractValidationError("allowlisted_duplicate_groups must be a list of path lists")
    return {tuple(sorted(normalize_repo_path(path, "allowlist") for path in group)) for group in groups}



def _duplicate_groups(hashes: dict[str, dict[str, Any]], allowed: set[tuple[str, ...]], config: dict[str, Any]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path, entry in hashes.items():
        by_hash[_sha(entry.get("sha256"), path)].append(path)
    groups: list[dict[str, Any]] = []
    for digest, paths in sorted(by_hash.items()):
        if len(paths) < 2:
            continue
        paths = sorted(paths)
        explicit_allow = tuple(paths) in allowed
        classification, default_blocking = classify_duplicate(paths, config)
        allowlisted = explicit_allow or not default_blocking
        groups.append({
            "sha256": digest,
            "paths": paths,
            "file_count": len(paths),
            "schema_duplicate": all(path.endswith(".schema.yaml") for path in paths),
            "allowlisted": allowlisted,
            "release_blocking": not allowlisted,
            "classification": "EXPLICIT_ALLOWLIST" if explicit_allow else classification,
        })
    return groups

def run_module(inputs: dict, config: dict | None = None) -> dict:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = require_config(config)
    missing = sorted({"source_tree_manifest", "file_hash_manifest"} - set(inputs))
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")

    source = _index(_entries(inputs["source_tree_manifest"], "source_tree_manifest"), "source_tree_manifest", False)
    hashes = _index(_entries(inputs["file_hash_manifest"], "file_hash_manifest"), "file_hash_manifest", True)
    if set(source) != set(hashes):
        raise ContractValidationError(
            "manifest path coverage mismatch: "
            f"missing_hashes={sorted(set(source) - set(hashes))[:5]}, "
            f"unknown_hashes={sorted(set(hashes) - set(source))[:5]}"
        )

    allowed = _allowlisted_groups(config)
    groups = _duplicate_groups(hashes, allowed, config)

    blocking = sum(bool(item["release_blocking"]) for item in groups)
    payload = {"paths": sorted(source), "groups": groups}
    artifact = envelope("duplicate_file_report", payload, config)
    artifact.update({
        "checked_file_count": len(source),
        "duplicate_group_count": len(groups),
        "schema_duplicate_group_count": sum(bool(item["schema_duplicate"]) for item in groups),
        "blocking_duplicate_group_count": blocking,
        "duplicate_groups": groups,
        "duplicate_hashes_detected": bool(groups),
        "schemas_duplicate_check": True,
        "status": "FAIL" if blocking else "PASS",
        "release_blocking": bool(blocking),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    })
    validate_artifact(artifact, "duplicate_file_report.schema.yaml", "duplicate_file_report")
    return module_result(
        "P0.S5.M01", "duplicate_file_detector",
        ["source_tree_manifest", "file_hash_manifest"], "duplicate_file_report", artifact,
    )
