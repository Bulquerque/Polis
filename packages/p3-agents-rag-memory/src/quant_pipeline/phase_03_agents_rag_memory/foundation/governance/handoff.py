from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
import logging
from typing import Any

from .canonical import (
    extract_records,
    record_identity,
    require_no_forbidden_fields,
    stable_sha256,
)
from .errors import Issue, S1ContractError
from .models import ExecutionProfile, S1Settings, ValidationStatus
from .schema_registry import SchemaRegistry


LOGGER = logging.getLogger(__name__)

REQUIRED_INPUTS = (
    "clean_context_source_panel",
    "clean_document_panel",
    "clean_event_reference_panel",
    "source_quality_panel",
    "context_handoff_manifest",
    "phase3_handoff_manifest",
)

DATA_ARTIFACTS = REQUIRED_INPUTS[:4]


def _log_event(event: str, **dimensions: Any) -> None:
    payload = {"event": event, **dimensions}
    LOGGER.info(json.dumps(payload, sort_keys=True, default=str))


def _require_inputs(inputs: dict[str, Any], required: tuple[str, ...]) -> None:
    if not isinstance(inputs, dict):
        raise S1ContractError("P3_S1_INPUT_INVALID", "inputs must be a mapping")
    missing = [name for name in required if name not in inputs]
    if missing:
        raise S1ContractError(
            "P3_S1_REQUIRED_ARTIFACT_MISSING",
            f"Missing required inputs: {missing}",
        )


def _artifact_ref(
    name: str,
    artifact: dict[str, Any],
    schema: dict[str, Any],
    registry_record: Any,
) -> dict[str, Any]:
    records = extract_records(artifact, name)
    observed_hash = str(artifact.get("content_hash") or stable_sha256(artifact))
    return {
        "artifact_name": name,
        "artifact_id": str(artifact["artifact_id"]),
        "schema_id": f"{name}.{schema.get('schema_version', 'unknown')}",
        "schema_version": str(schema.get("schema_version", "unknown")),
        "schema_binding": "EXTERNAL_AUTHORITY",
        "schema_sha256": registry_record.sha256,
        "schema_authority": registry_record.authority,
        "schema_authority_path": registry_record.path,
        "content_hash": observed_hash,
        "lineage_id": str(artifact["lineage_id"]),
        "pipeline_version": str(artifact["pipeline_version"]),
        "grain": list(schema.get("grain", [])),
        "row_count": len(records),
        "validation_status": ValidationStatus.READY.value,
    }


def _manifest_ref(name: str, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_name": name,
        "artifact_id": str(manifest.get("artifact_id") or manifest.get("handoff_id")),
        "content_hash": stable_sha256(manifest),
        "lineage_id": str(manifest["lineage_id"]),
        "pipeline_version": str(manifest["pipeline_version"]),
    }


def _validate_target_manifest(
    *,
    manifest_name: str,
    manifest: dict[str, Any],
    expected_refs: list[dict[str, Any]],
    settings: S1Settings,
) -> list[Issue]:
    issues: list[Issue] = []
    target_phase = str(manifest.get("target_phase", ""))
    if target_phase != "phase_03_agents_rag_memory":
        raise S1ContractError(
            "P3_S1_TARGET_PHASE_MISMATCH",
            f"{manifest_name}.target_phase={target_phase!r} is not P3",
        )

    expected_ids = {ref["artifact_id"] for ref in expected_refs}
    legacy_ids = {str(value) for value in manifest.get("artifact_ids", [])}
    if not expected_ids.issubset(legacy_ids):
        raise S1ContractError(
            "P3_S1_MANIFEST_ARTIFACT_ID_MISMATCH",
            f"{manifest_name}.artifact_ids does not include all P3 data artifacts",
        )

    target_ids_raw = manifest.get("target_artifact_ids")
    if isinstance(target_ids_raw, list):
        target_ids = {str(value) for value in target_ids_raw}
        if target_ids != expected_ids:
            raise S1ContractError(
                "P3_S1_TARGET_ARTIFACT_ID_MISMATCH",
                f"{manifest_name}.target_artifact_ids differs from observed P3 artifacts",
            )
    else:
        issues.append(
            Issue(
                code="P3_S1_PRECISE_TARGET_IDS_MISSING",
                severity="WARNING",
                message=f"{manifest_name} has no target_artifact_ids",
                artifact_name=manifest_name,
            )
        )

    refs_raw = manifest.get("artifact_refs")
    if not isinstance(refs_raw, list):
        issue = Issue(
            code="P3_S1_PRECISE_ARTIFACT_REFS_MISSING",
            severity="WARNING",
            message=f"{manifest_name} has no artifact_refs",
            artifact_name=manifest_name,
        )
        issues.append(issue)
        if (
            settings.execution_profile is ExecutionProfile.QUALIFICATION
            and settings.require_precise_manifest_refs_in_qualification
        ):
            raise S1ContractError(
                "P3_S1_PRECISE_MANIFEST_REQUIRED",
                f"{manifest_name} requires artifact_refs in qualification mode",
                issues=[issue],
            )
        return issues

    refs_by_name: dict[str, dict[str, Any]] = {}
    for raw in refs_raw:
        if not isinstance(raw, dict) or not raw.get("artifact_name"):
            raise S1ContractError(
                "P3_S1_MANIFEST_REF_INVALID",
                f"{manifest_name}.artifact_refs contains an invalid entry",
            )
        refs_by_name[str(raw["artifact_name"])] = raw

    for expected in expected_refs:
        name = expected["artifact_name"]
        observed = refs_by_name.get(name)
        if observed is None:
            raise S1ContractError(
                "P3_S1_MANIFEST_REF_MISSING",
                f"{manifest_name} has no reference for {name}",
            )
        if str(observed.get("artifact_id")) != expected["artifact_id"]:
            raise S1ContractError(
                "P3_S1_MANIFEST_REF_ID_MISMATCH",
                f"{manifest_name} reference ID mismatch for {name}",
            )
        expected_hash = observed.get("content_hash")
        if expected_hash:
            if str(expected_hash) != expected["content_hash"]:
                raise S1ContractError(
                    "P3_S1_HASH_MISMATCH",
                    f"{manifest_name} content hash mismatch for {name}",
                )
        elif settings.strict_manifest_hashes:
            issues.append(
                Issue(
                    code="P3_S1_MANIFEST_HASH_MISSING",
                    severity="WARNING",
                    message=f"{manifest_name} reference has no content_hash for {name}",
                    artifact_name=manifest_name,
                )
            )
        lineage = observed.get("lineage_id")
        if lineage and str(lineage) != expected["lineage_id"]:
            raise S1ContractError(
                "P3_S1_LINEAGE_MISMATCH",
                f"{manifest_name} lineage mismatch for {name}",
            )
    return issues


def _build_record_index(
    artifacts: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[Issue]]:
    index: list[dict[str, Any]] = []
    issues: list[Issue] = []
    for artifact_name in (
        "clean_context_source_panel",
        "clean_document_panel",
        "clean_event_reference_panel",
    ):
        records = extract_records(artifacts[artifact_name], artifact_name)
        for position, row in enumerate(records):
            record_id = record_identity(row, position)
            source_id = row.get("source_id")
            if source_id in (None, ""):
                issues.append(
                    Issue(
                        code="P3_S1_SOURCE_ID_MISSING",
                        severity="WARNING",
                        message="Record cannot be joined to source quality",
                        artifact_name=artifact_name,
                        record_id=record_id,
                        field="source_id",
                    )
                )
            index.append(
                {
                    "artifact_name": artifact_name,
                    "record_id": record_id,
                    "source_id": None if source_id in (None, "") else str(source_id),
                    "position": position,
                    "lineage_id": row.get("lineage_id"),
                    "available_at": row.get("available_at"),
                }
            )
    return index, issues


def validate_phase2_handoff(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    registry: SchemaRegistry | None = None,
) -> dict[str, Any]:
    """Validate the six official P2→P3 inputs without mutating or repairing them."""

    settings = S1Settings.from_mapping(config)
    registry = registry or SchemaRegistry.from_config(config)
    _log_event("module_started", module_id="P3.S1.M01")
    _require_inputs(inputs, REQUIRED_INPUTS)
    immutable_copy = deepcopy(inputs)

    validated: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_INPUTS:
        validated[name] = registry.validate_external(name, inputs[name])

    artifact_ids = [str(validated[name]["artifact_id"]) for name in DATA_ARTIFACTS]
    if len(set(artifact_ids)) != len(artifact_ids):
        raise S1ContractError(
            "P3_S1_DUPLICATE_ARTIFACT_ID",
            "P2 data artifacts must have unique artifact_id values",
        )

    refs = [
        _artifact_ref(name, validated[name], registry.external(name), registry.authority_record(name))
        for name in DATA_ARTIFACTS
    ]

    issues: list[Issue] = []
    for manifest_name in ("context_handoff_manifest", "phase3_handoff_manifest"):
        issues.extend(
            _validate_target_manifest(
                manifest_name=manifest_name,
                manifest=validated[manifest_name],
                expected_refs=refs,
                settings=settings,
            )
        )

    context_targets = validated["context_handoff_manifest"].get("target_artifact_ids")
    phase3_targets = validated["phase3_handoff_manifest"].get("target_artifact_ids")
    if isinstance(context_targets, list) and isinstance(phase3_targets, list):
        if {str(value) for value in context_targets} != {
            str(value) for value in phase3_targets
        }:
            raise S1ContractError(
                "P3_S1_MANIFESTS_DISAGREE",
                "context_handoff_manifest and phase3_handoff_manifest disagree",
            )

    quality_records = extract_records(validated["source_quality_panel"], "source_quality_panel")
    quality_source_ids = [str(row["source_id"]) for row in quality_records]
    duplicates = sorted(
        source_id for source_id, count in Counter(quality_source_ids).items() if count > 1
    )
    if duplicates:
        raise S1ContractError(
            "P3_S1_DUPLICATE_SOURCE_QUALITY",
            f"source_quality_panel contains duplicate source_id values: {duplicates[:10]}",
        )

    record_index, index_issues = _build_record_index(validated)
    if not record_index:
        raise S1ContractError(
            "P3_S1_EMPTY_CONTEXT_HANDOFF",
            "P2 handoff contains no context, document or event records",
        )
    issues.extend(index_issues)
    quality_set = set(quality_source_ids)
    orphan_ids = sorted(
        {
            str(record["source_id"])
            for record in record_index
            if record["source_id"] is not None and record["source_id"] not in quality_set
        }
    )
    if orphan_ids:
        raise S1ContractError(
            "P3_S1_ORPHAN_SOURCE_REFERENCE",
            f"Records reference source IDs absent from source_quality_panel: {orphan_ids[:10]}",
        )

    if inputs != immutable_copy:
        raise S1ContractError(
            "P3_S1_INPUT_MUTATION_DETECTED",
            "P3.S1.M01 mutated an input artifact",
        )

    status = ValidationStatus.DEGRADED if issues else ValidationStatus.READY
    output: dict[str, Any] = {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p3.s1.validated_phase2_handoff.v2",
        "handoff_id": str(validated["phase3_handoff_manifest"]["handoff_id"]),
        "source_pipeline_version": str(validated["phase3_handoff_manifest"]["pipeline_version"]),
        "target_phase": "phase_03_agents_rag_memory",
        "validation_status": status.value,
        "artifacts": refs,
        "manifests": [
            _manifest_ref("context_handoff_manifest", validated["context_handoff_manifest"]),
            _manifest_ref("phase3_handoff_manifest", validated["phase3_handoff_manifest"]),
        ],
        "record_index": sorted(
            record_index,
            key=lambda row: (row["artifact_name"], row["position"], row["record_id"]),
        ),
        "cross_artifact_checks": {
            "six_required_artifacts_present": True,
            "schema_versions_compatible": True,
            "manifest_artifact_ids_match": True,
            "manifest_hashes_match_when_declared": True,
            "artifact_ids_unique": True,
            "source_quality_references_closed": True,
            "input_immutability_preserved": True,
        },
        "issues": [issue.to_dict() for issue in issues],
        "lineage_id": f"lineage-p3-s1-handoff-{stable_sha256(refs)[:20]}",
    }
    authority_rows = [registry.authority_record(name) for name in REQUIRED_INPUTS]
    output["schema_authority"] = {
        "mode": "GLOBAL_REPOSITORY" if registry.authority else "LOCAL_MIRROR",
        "records": [
            {"artifact_name": row.artifact_name, "path": row.path, "sha256": row.sha256, "authority": row.authority}
            for row in authority_rows
        ],
        "aggregate_sha256": stable_sha256([(row.artifact_name, row.sha256) for row in authority_rows]),
    }
    output["content_hash"] = stable_sha256(output)
    registry.validate_internal("validated_phase2_handoff", output)
    require_no_forbidden_fields(output, "validated_phase2_handoff")
    _log_event(
        "module_succeeded",
        module_id="P3.S1.M01",
        validation_status=status.value,
        artifact_count=len(refs),
        record_count=len(record_index),
        warning_count=len(issues),
    )
    return output


