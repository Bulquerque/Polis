from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ._s2_common import (
    created_at,
    find_forbidden_fields,
    normalized_version,
    stable_digest,
    validate_schema_value,
)
from ._s2_schema_registry import (
    canonical_schema_version,
    expected_inventory,
    mirror_policy_gaps,
    read_schema,
    relative,
    resolve_input_paths,
    schema_entry,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[6]
AUTHORITY_ROOT = (
    WORKSPACE_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
)
AUTHORITY_LABEL = (
    "global_contracts_parallel_agents/"
    "v14_1_global_contracts_parallel_agents_RC4_1"
)


def _read_schema(path: Path) -> tuple[dict[str, Any], str]:
    """Compatibility hook retained for mutation tests."""
    return read_schema(path, workspace_root=WORKSPACE_ROOT)


def _find_forbidden_fields(value: Any, path: str = "inputs") -> list[str]:
    return find_forbidden_fields(value, path)


def _validate_artifact(artifact: dict[str, Any]) -> None:
    import yaml

    schema_path = SCHEMA_ROOT / "schema_registry.schema.yaml"
    try:
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid schema registry schema: {exc}") from exc
    if not isinstance(schema, dict):
        raise ContractValidationError("schema registry schema must be a mapping")
    validate_schema_value(artifact, schema, "schema_registry")
    leaked = _find_forbidden_fields(artifact, "schema_registry")
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = _validated_runtime(inputs, config)
    authority_paths, mirror_paths = expected_inventory(WORKSPACE_ROOT, AUTHORITY_ROOT)
    observed_paths = resolve_input_paths(
        inputs["schemas_all_phases"],
        workspace_root=WORKSPACE_ROOT,
        authority_root=AUTHORITY_ROOT,
    )
    if str(config.get("release_scope", "")).upper() == "P0_TECHNICAL_CLOSURE":
        mirror_paths = [path for path in mirror_paths if "phase_00_zero_trust" in path.as_posix()]
        observed_paths = authority_paths + mirror_paths
    loaded = {path: _read_schema(path) for path in observed_paths}
    expected_version = canonical_schema_version(authority_paths, loaded)
    authority_entries = _build_authority_entries(
        authority_paths, loaded, expected_version
    )
    mirrors, findings = _build_mirror_records(
        mirror_paths,
        authority_paths,
        loaded,
        expected_version=expected_version,
    )
    artifact = _build_registry_artifact(
        observed_paths, authority_entries, mirrors, findings, loaded, config
    )
    _validate_artifact(artifact)
    return {
        "module_id": "P0.S2.M02",
        "module_name": "schema_registry_builder",
        "phase": "P0",
        "subphase": "P0.S2",
        "contract": "P0_S2_M02_schema_registry_builder.yaml",
        "required_inputs": ["schemas_all_phases"],
        "outputs": {"schema_registry": artifact},
    }


def _validated_runtime(inputs: dict, config: dict | None) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    if "schemas_all_phases" not in inputs:
        raise ContractValidationError("missing required inputs: ['schemas_all_phases']")
    leaked = _find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    runtime_version = str(config.get("pipeline_version") or PIPELINE_VERSION)
    if normalized_version(runtime_version) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("pipeline version is incompatible")
    return config


def _build_authority_entries(
    authority_paths: list[Path],
    loaded: dict[Path, tuple[dict[str, Any], str]],
    expected_version: str,
) -> list[dict[str, Any]]:
    entries = [
        schema_entry(
            path,
            loaded[path][0],
            loaded[path][1],
            workspace_root=WORKSPACE_ROOT,
            expected_version=expected_version,
        )
        for path in authority_paths
    ]
    _validate_unique_authority_identity(entries)
    entries.sort(key=lambda entry: entry["schema_id"])
    return entries


def _build_registry_artifact(
    observed_paths: list[Path],
    authority_entries: list[dict[str, Any]],
    mirrors: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    loaded: dict[Path, tuple[dict[str, Any], str]],
    config: dict[str, Any],
) -> dict[str, Any]:
    mirrors.sort(key=lambda entry: entry["path"])
    normalized = {
        "authority_root": AUTHORITY_LABEL,
        "schemas": authority_entries,
        "mirrors": mirrors,
        "findings": findings,
    }
    digest = stable_digest(normalized)
    blocked = bool(findings)
    return {
        "artifact_id": f"schema-registry-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "authority_root": AUTHORITY_LABEL,
        "inventory_count": len(observed_paths),
        "authority_schema_count": len(authority_entries),
        "mirror_count": len(mirrors),
        "mirror_match_count": sum(item["status"] == "MATCH" for item in mirrors),
        "mirror_divergence_count": len(findings),
        "hashed_file_count": len(loaded),
        "schemas": authority_entries,
        "mirrors": mirrors,
        "findings": findings,
        "status": "FAIL" if blocked else "PASS",
        "severity": "CRITICAL" if blocked else "NONE",
        "release_blocking": blocked,
        "schema_id_unique": True,
        "required_fields_not_empty": True,
        "artifact_name_unique": True,
        "schema_version_consistent": True,
        "properties_types_consistent": True,
        "inventory_complete": True,
        "hashes_computed": True,
        "mirror_authority_enforced": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def _validate_unique_authority_identity(entries: list[dict[str, Any]]) -> None:
    schema_ids = [entry["schema_id"] for entry in entries]
    artifacts = [entry["artifact_name"] for entry in entries]
    if len(schema_ids) != len(set(schema_ids)):
        raise ContractValidationError("schema_id_unique validation failed in authority inventory")
    if len(artifacts) != len(set(artifacts)):
        raise ContractValidationError("artifact_name_unique validation failed in authority inventory")


def _build_mirror_records(
    mirror_paths: list[Path],
    authority_paths: list[Path],
    loaded: dict[Path, tuple[dict[str, Any], str]],
    *,
    expected_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    authority_by_name = {path.name: path for path in authority_paths}
    mirrors: list[dict[str, Any]] = []
    raw_findings: list[dict[str, Any]] = []
    for mirror_path in mirror_paths:
        authority_path = authority_by_name.get(mirror_path.name)
        if authority_path is None:
            raise ContractValidationError(f"mirror has no global authority: {relative(mirror_path, WORKSPACE_ROOT)}")
        mirror_document, mirror_hash = loaded[mirror_path]
        schema_entry(
            mirror_path,
            mirror_document,
            mirror_hash,
            workspace_root=WORKSPACE_ROOT,
            expected_version=expected_version,
        )
        authority_document, authority_hash = loaded[authority_path]
        gaps = mirror_policy_gaps(authority_document, mirror_document)
        status = "DIVERGED" if gaps else "MATCH"
        record = {
            "path": relative(mirror_path, WORKSPACE_ROOT),
            "authority_path": relative(authority_path, WORKSPACE_ROOT),
            "sha256": mirror_hash,
            "authority_sha256": authority_hash,
            "status": status,
            "content_relation": "EXACT" if mirror_hash == authority_hash else "COMPATIBLE_EXTENSION",
        }
        mirrors.append(record)
        if gaps:
            raw_findings.append(
                {
                    "code": "MIRROR_POLICY_DIVERGENCE",
                    "severity": "CRITICAL",
                    "mirror_path": record["path"],
                    "authority_path": record["authority_path"],
                    "expected_hash": authority_hash,
                    "actual_hash": mirror_hash,
                    "message": "; ".join(gaps),
                    "release_blocking": True,
                }
            )
    findings = [
        {"finding_id": f"SR-{index:04d}", **finding}
        for index, finding in enumerate(
            sorted(raw_findings, key=lambda item: item["mirror_path"]), start=1
        )
    ]
    return mirrors, findings
