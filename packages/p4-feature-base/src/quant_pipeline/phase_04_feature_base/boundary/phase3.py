from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import BoundaryContractError, BoundaryErrorCode
from ..models import ArtifactReference, ExecutionContext
from ..runtime.artifacts import materialized_mapping, require_inputs, validate_artifact
from ..runtime.artifacts import is_compatible_upstream_pipeline
from ..runtime.canonical import content_hash
from ..runtime.forbidden import assert_reference_only_manifest, scan_fields
from ..runtime.outputs import build_artifact

REQUIRED_ARTIFACTS = (
    "social_feature_panel", "evidence_tag_panel", "agent_disagreement_panel",
    "context_memory_feature_panel", "hypothesis_registry",
)


def _entry_map(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    entries = manifest.get("entries")
    if entries is None:
        return {}
    if not isinstance(entries, list):
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH, "entries must be a list", path="phase4_social_handoff_manifest.entries"
        )
    result: dict[str, Mapping[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or not entry.get("artifact_name"):
            raise BoundaryContractError(
                BoundaryErrorCode.MANIFEST_MISMATCH, "invalid manifest entry", path=f"entries[{index}]"
            )
        name = str(entry["artifact_name"])
        if name in result:
            raise BoundaryContractError(BoundaryErrorCode.MANIFEST_MISMATCH, f"duplicate entry {name!r}")
        result[name] = entry
    return result


def _validate_artifacts(
    inputs: Mapping[str, Any], context: ExecutionContext, schema_root: Any
) -> tuple[list[ArtifactReference], dict[str, Mapping[str, Any]]]:
    validated: list[ArtifactReference] = []
    raw: dict[str, Mapping[str, Any]] = {}
    for name in REQUIRED_ARTIFACTS:
        raw[name] = materialized_mapping(inputs[name], name)
        validated.append(validate_artifact(
            name, inputs[name], context=context, schema_path=schema_root / f"{name}.schema.yaml",
            private_scan=True, compatibility_hash=None,
        ))
    return validated, raw


def _validate_manifest_identity(manifest: Mapping[str, Any], context: ExecutionContext) -> None:
    expected_values = (
        ("run_id", context.run_id, BoundaryErrorCode.RUN_MISMATCH),
        ("cycle_id", context.cycle_id, BoundaryErrorCode.CYCLE_MISMATCH),
        ("pipeline_version", context.pipeline_version, BoundaryErrorCode.PIPELINE_VERSION_MISMATCH),
    )
    for field, expected, code in expected_values:
        declared = manifest.get(field)
        if (
            declared is not None
            and str(declared) != expected
            and not is_compatible_upstream_pipeline(str(declared), context)
        ):
            raise BoundaryContractError(
                code, f"expected {expected!r}, got {declared!r}",
                path=f"phase4_social_handoff_manifest.{field}",
            )


def _validate_manifest_entries(
    entries: Mapping[str, Mapping[str, Any]],
    validated: list[ArtifactReference],
    raw: Mapping[str, Mapping[str, Any]],
) -> None:
    if entries and set(entries) != set(REQUIRED_ARTIFACTS):
        difference = sorted(set(entries) ^ set(REQUIRED_ARTIFACTS))
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH,
            f"manifest entries differ from required artifacts: {difference}",
        )
    for ref in validated:
        entry = entries.get(ref.artifact_name)
        if entry is not None:
            _validate_entry(ref, entry, raw[ref.artifact_name])


def _validate_entry(
    ref: ArtifactReference, entry: Mapping[str, Any], raw: Mapping[str, Any]
) -> None:
    path = f"entries.{ref.artifact_name}"
    if str(entry.get("artifact_id")) != ref.artifact_id:
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH, "artifact_id mismatch", path=path
        )
    expected_hash = str(entry.get("content_hash") or "")
    actual_hash = content_hash(raw)
    if expected_hash and expected_hash != actual_hash:
        raise BoundaryContractError(
            BoundaryErrorCode.HASH_MISMATCH,
            f"expected {expected_hash}, computed {actual_hash}", path=f"{path}.content_hash",
        )
    if entry.get("row_count") is not None and int(entry["row_count"]) != ref.row_count:
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH, "row_count mismatch", path=f"{path}.row_count"
        )


def _quality_gate(manifest: Mapping[str, Any], context: ExecutionContext) -> str:
    quality = str(manifest.get("quality_status") or "LEGACY_UNVERIFIED").upper()
    if quality in {"BLOCK", "BLOCKED", "FAILED"}:
        raise BoundaryContractError(BoundaryErrorCode.QUALITY_BLOCKED, f"P3 quality status is {quality}")
    if quality == "DEGRADED" and not context.allow_degraded_handoffs:
        raise BoundaryContractError(BoundaryErrorCode.QUALITY_BLOCKED, "degraded P3 handoff is not authorized")
    return quality


def validate_phase3_handoff(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    schema_root: Any,
    output_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    require_inputs(inputs, list(REQUIRED_ARTIFACTS) + ["phase4_social_handoff_manifest"])
    validated, raw = _validate_artifacts(inputs, context, schema_root)
    manifest = materialized_mapping(
        inputs["phase4_social_handoff_manifest"], "phase4_social_handoff_manifest"
    )
    scan_fields(manifest, private=True, path="phase4_social_handoff_manifest")
    assert_reference_only_manifest(manifest)
    _validate_manifest_identity(manifest, context)
    _validate_manifest_entries(_entry_map(manifest), validated, raw)
    quality = _quality_gate(manifest, context)
    capabilities = [
        {"capability": name, "artifact_name": name, "status": "AVAILABLE",
         "reason": None, "required": True}
        for name in REQUIRED_ARTIFACTS
    ]
    bundle = build_artifact(
        name="validated_phase3_bundle", module_id="P4.S1.M02", context=context,
        records=[ref.to_dict() for ref in validated], schema=output_schemas["validated_phase3_bundle"],
        extra={"source_manifest_id": str(manifest.get("artifact_id")), "quality_status": quality},
    )
    capability = build_artifact(
        name="phase3_capability_matrix", module_id="P4.S1.M02", context=context,
        records=capabilities, schema=output_schemas["phase3_capability_matrix"],
    )
    return {"validated_phase3_bundle": bundle, "phase3_capability_matrix": capability}
