from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ...shared.assets import source_or_packaged_root
from .canonical import (
    content_hash,
    ensure_mapping,
    extract_records,
    format_utc,
    lineage_token,
    parse_aware_datetime,
    parse_cycle_id,
    require_fields,
    require_no_forbidden_fields,
    require_no_secrets,
    stable_sha256,
)
from .errors import Issue, S3ContractError
from .schemas import SchemaRegistry
from .validators import normalize_promoted_patch

REQUIRED_INPUTS = (
    "retro_memory_update_package",
    "phase3_retro_handoff_manifest",
    "phase3_run_snapshot",
    "retro_patch_compatibility_config",
)
_SCHEMA_PATH = "schemas/internal/active_retro_policy_patch.schema.yaml"


@dataclass(frozen=True, slots=True)
class _RetroInputs:
    snapshot: dict[str, Any]
    package: dict[str, Any]
    manifest: dict[str, Any]
    policy: dict[str, Any]
    as_of: datetime
    current_cycle: int
    processed_at: str
    registry: SchemaRegistry


def _schema_registry(config: dict[str, Any]) -> SchemaRegistry:
    package_root = config.get("package_root")
    root = Path(package_root) if package_root else source_or_packaged_root()
    return SchemaRegistry(root)


def _validated_inputs(
    inputs: dict[str, Any],
    execution: dict[str, Any],
) -> _RetroInputs:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    if missing:
        raise S3ContractError("P3_S3_M01_INPUT_INVALID", f"missing required inputs: {missing}")
    values = {name: deepcopy(ensure_mapping(inputs[name], name)) for name in REQUIRED_INPUTS}
    for name, value in values.items():
        require_no_forbidden_fields(value, name)
        require_no_secrets(value, name)

    snapshot = values["phase3_run_snapshot"]
    package = values["retro_memory_update_package"]
    manifest = values["phase3_retro_handoff_manifest"]
    policy = values["retro_patch_compatibility_config"]
    require_fields(snapshot, ["identity", "temporal", "lineage_id"], location="phase3_run_snapshot")
    require_fields(package, ["artifact_id", "lineage_id"], location="retro_memory_update_package")
    require_fields(
        manifest,
        ["artifact_id", "created_at", "lineage_id", "pipeline_version"],
        location="phase3_retro_handoff_manifest",
    )
    require_fields(
        policy,
        ["allowed_change_types", "promoted_status_required", "same_cycle_forbidden", "target_versions"],
        location="retro_patch_compatibility_config",
    )
    as_of = parse_aware_datetime(snapshot["temporal"]["as_of"], field="phase3_run_snapshot.temporal.as_of")
    current_cycle = parse_cycle_id(execution.get("current_cycle_id"), field="current_cycle_id")
    processed_at = format_utc(parse_aware_datetime(execution.get("processed_at"), field="processed_at"))
    _validate_source_time(package, "retro_memory_update_package", as_of)
    _validate_source_time(manifest, "phase3_retro_handoff_manifest", as_of)
    if lineage_token(package) != lineage_token(manifest):
        raise S3ContractError("P3_S3_M01_LINEAGE_MISMATCH", "P9 package and manifest lineage differ")
    return _RetroInputs(
        snapshot=snapshot,
        package=package,
        manifest=manifest,
        policy=policy,
        as_of=as_of,
        current_cycle=current_cycle,
        processed_at=processed_at,
        registry=_schema_registry(execution),
    )


def _validate_source_time(value: dict[str, Any], label: str, as_of: datetime) -> None:
    created_at = value.get("created_at") or value.get("valid_from")
    if created_at is None:
        return
    if parse_aware_datetime(created_at, field=f"{label}.created_at") > as_of:
        raise S3ContractError("P3_S3_M01_TEMPORAL_VIOLATION", f"{label} created after as_of")


def _patch_candidates(package: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in extract_records(package, "retro_memory_update_package"):
        nested = row.get("agent_instruction_updates")
        if isinstance(nested, list):
            parent = {key: value for key, value in row.items() if key != "agent_instruction_updates"}
            candidates.extend(_mapping_items(nested, "agent_instruction_updates", parent))
        if any(key in row for key in ("patch_id", "change_type", "change_target", "promotion_status")):
            candidates.append(row)
    top_level = package.get("patches")
    if isinstance(top_level, list):
        candidates.extend(_mapping_items(top_level, "patches"))
    unique = {stable_sha256(candidate): candidate for candidate in candidates}
    return [unique[key] for key in sorted(unique)]


def _mapping_items(
    values: list[Any],
    label: str,
    parent: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            raise S3ContractError("P3_S3_M01_PATCH_NOT_MAPPING", f"{label} item must be mapping")
        items.append({**(parent or {}), **item})
    return items


def _base_output(prepared: _RetroInputs) -> dict[str, Any]:
    return {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p3.s3.active_retro_policy_patch.v2",
        "run_id": prepared.snapshot["identity"]["run_id"],
        "snapshot_id": prepared.snapshot["identity"]["snapshot_id"],
        "current_cycle_id": prepared.current_cycle,
        "source_package": {
            "artifact_id": prepared.package["artifact_id"],
            "lineage_id": prepared.package["lineage_id"],
        },
        "source_manifest": {
            "artifact_id": prepared.manifest["artifact_id"],
            "lineage_id": prepared.manifest["lineage_id"],
        },
        "created_at": prepared.processed_at,
    }


def _no_patch_output(prepared: _RetroInputs) -> dict[str, Any]:
    seed = [
        prepared.package["artifact_id"],
        prepared.manifest["artifact_id"],
        prepared.snapshot["identity"]["snapshot_id"],
    ]
    return {
        **_base_output(prepared),
        "status": "NO_PATCH",
        "patch": None,
        "issues": [
            Issue(
                "P3_S3_M01_NO_PROMOTED_PATCH",
                "INFO",
                "No explicit promoted patch was present; contextual memory remains inactive",
                "retro_memory_update_package",
            ).as_dict()
        ],
        "lineage_id": f"lineage-active-retro-{stable_sha256(seed)[:16]}",
    }


def _active_patch_output(prepared: _RetroInputs, patch: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_promoted_patch(
        patch,
        policy=prepared.policy,
        current_cycle=prepared.current_cycle,
        as_of=prepared.as_of,
    )
    seed = [patch["patch_id"], prepared.snapshot["identity"]["snapshot_id"]]
    return {
        **_base_output(prepared),
        "status": "ACTIVE",
        "patch": normalized,
        "issues": [],
        "lineage_id": f"lineage-active-retro-{stable_sha256(seed)[:16]}",
    }


def _finalize(prepared: _RetroInputs, output: dict[str, Any]) -> dict[str, Any]:
    output["content_hash"] = content_hash(output)
    prepared.registry.validate(_SCHEMA_PATH, output, label="active_retro_policy_patch")
    return output


def ingest_promoted_retro_update(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and materialize one prior-cycle promoted patch without applying it."""

    prepared = _validated_inputs(inputs, dict(config or {}))
    candidates = _patch_candidates(prepared.package)
    if not candidates:
        return _finalize(prepared, _no_patch_output(prepared))
    if len(candidates) != 1:
        raise S3ContractError(
            "P3_S3_M01_MULTIPLE_ACTIVE_PATCHES",
            f"expected one patch candidate, found {len(candidates)}",
        )
    return _finalize(prepared, _active_patch_output(prepared, candidates[0]))
