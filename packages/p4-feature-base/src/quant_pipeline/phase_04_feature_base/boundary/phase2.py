from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import BoundaryContractError, BoundaryErrorCode
from ..models import ArtifactReference, ExecutionContext
from ..runtime.artifacts import materialized_mapping, require_inputs, validate_artifact
from ..runtime.forbidden import assert_reference_only_manifest, scan_fields
from ..runtime.outputs import build_artifact
from ..runtime.schema_validation import load_schema, validate_legacy_upstream_schema

REQUIRED_ARTIFACTS = (
    "clean_underlying_panel", "clean_macro_br_panel", "clean_macro_us_panel",
    "clean_benchmark_panel", "clean_calendar_panel", "clean_corporate_actions_panel",
    "quality_report_phase_2",
)
EXTENSION_ARTIFACTS = (
    "clean_underlying_trade_panel", "clean_option_contract_panel", "clean_option_quotes_panel",
    "clean_event_reference_panel", "clean_context_source_panel", "clean_document_panel",
    "source_quality_panel", "clean_liquidity_reference_panel", "clean_fundamental_panel",
    "clean_curve_term_structure_panel",
)


def _quality_gate(report: Mapping[str, Any], context: ExecutionContext) -> str:
    status = str(report.get("status") or report.get("quality_status") or "LEGACY_UNVERIFIED").upper()
    if status in {"BLOCK", "BLOCKED", "FAILED"}:
        raise BoundaryContractError(BoundaryErrorCode.QUALITY_BLOCKED, f"P2 quality status is {status}")
    if status == "DEGRADED" and not context.allow_degraded_handoffs:
        raise BoundaryContractError(
            BoundaryErrorCode.QUALITY_BLOCKED, "degraded P2 handoff requires explicit authorization"
        )
    return status


def _manifest_refs(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    refs = manifest.get("artifact_refs", [])
    if refs is None:
        return {}
    if not isinstance(refs, list):
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH,
            "artifact_refs must be a list",
            path="phase4_handoff_manifest.artifact_refs",
        )
    result: dict[str, Mapping[str, Any]] = {}
    for index, ref in enumerate(refs):
        if not isinstance(ref, Mapping) or not ref.get("artifact_name"):
            raise BoundaryContractError(
                BoundaryErrorCode.MANIFEST_MISMATCH, "invalid artifact reference", path=f"artifact_refs[{index}]"
            )
        name = str(ref["artifact_name"])
        if name in result:
            raise BoundaryContractError(
                BoundaryErrorCode.MANIFEST_MISMATCH,
                f"duplicate artifact reference {name!r}",
                path=f"artifact_refs[{index}]",
            )
        result[name] = ref
    return result


def _validate_required(
    inputs: Mapping[str, Any], context: ExecutionContext, schema_root: Any
) -> tuple[list[ArtifactReference], dict[str, ArtifactReference]]:
    validated: list[ArtifactReference] = []
    by_name: dict[str, ArtifactReference] = {}
    for name in REQUIRED_ARTIFACTS:
        ref = validate_artifact(
            name, inputs[name], context=context, schema_path=schema_root / f"{name}.schema.yaml",
            private_scan=False, compatibility_hash="P2",
        )
        validated.append(ref)
        by_name[name] = ref
    return validated, by_name


def _validate_manifest(
    payload: Any,
    context: ExecutionContext,
    schema_root: Any,
    validated: list[ArtifactReference],
    by_name: Mapping[str, ArtifactReference],
) -> Mapping[str, Any]:
    manifest = materialized_mapping(payload, "phase4_handoff_manifest")
    scan_fields(manifest, path="phase4_handoff_manifest")
    assert_reference_only_manifest(manifest)
    validate_legacy_upstream_schema(
        "phase4_handoff_manifest", manifest,
        load_schema(schema_root / "phase4_handoff_manifest.schema.yaml"), context.compatibility_mode,
    )
    if str(manifest.get("target_phase")) != "phase_04_feature_base":
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH, "target_phase must be phase_04_feature_base"
        )
    raw_artifact_ids = [str(value) for value in manifest.get("artifact_ids", [])]
    if len(raw_artifact_ids) != len(set(raw_artifact_ids)):
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH,
            "artifact_ids must be unique",
            path="phase4_handoff_manifest.artifact_ids",
        )
    artifact_ids = set(raw_artifact_ids)
    missing = {ref.artifact_id for ref in validated} - artifact_ids
    if missing:
        raise BoundaryContractError(
            BoundaryErrorCode.MANIFEST_MISMATCH, f"manifest is missing artifact IDs: {sorted(missing)}"
        )
    _validate_declared_references(_manifest_refs(manifest), by_name)
    return manifest


def _validate_declared_references(
    declared_refs: Mapping[str, Mapping[str, Any]], by_name: Mapping[str, ArtifactReference]
) -> None:
    for name, ref in by_name.items():
        declared = declared_refs.get(name)
        if declared is None:
            raise BoundaryContractError(
                BoundaryErrorCode.MANIFEST_MISMATCH,
                f"artifact {name!r} is materialized but absent from artifact_refs",
                path=f"phase4_handoff_manifest.artifact_refs.{name}",
            )
        if str(declared.get("artifact_id")) != ref.artifact_id:
            raise BoundaryContractError(
                BoundaryErrorCode.MANIFEST_MISMATCH, "artifact_id mismatch", path=f"artifact_refs.{name}"
            )
        declared_hash = declared.get("content_hash")
        if declared_hash and str(declared_hash) != ref.legacy_content_hash:
            raise BoundaryContractError(
                BoundaryErrorCode.HASH_MISMATCH,
                f"expected {declared_hash}, computed {ref.legacy_content_hash}",
                path=f"artifact_refs.{name}.content_hash",
            )


def _validate_extensions(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    schema_root: Any,
    manifest: Mapping[str, Any],
    required: list[ArtifactReference],
) -> tuple[list[ArtifactReference], list[dict[str, Any]]]:
    validated: list[ArtifactReference] = []
    required_by_name = {ref.artifact_name: ref for ref in required}
    capabilities = [
        _capability(name, available=required_by_name[name].row_count > 0, required=True)
        for name in REQUIRED_ARTIFACTS
    ]
    declared_refs = _manifest_refs(manifest)
    declared_ids = {str(value) for value in manifest.get("artifact_ids", [])}
    for name in EXTENSION_ARTIFACTS:
        if name not in inputs:
            capabilities.append(_capability(name, available=False, required=False))
            continue
        ref = validate_artifact(
            name, inputs[name], context=context, schema_path=schema_root / f"{name}.schema.yaml",
            private_scan=False, compatibility_hash="P2",
        )
        if ref.artifact_id not in declared_ids:
            raise BoundaryContractError(
                BoundaryErrorCode.MANIFEST_MISMATCH,
                f"optional artifact {name!r} is absent from artifact_ids",
                path="phase4_handoff_manifest.artifact_ids",
            )
        _validate_declared_references(declared_refs, {name: ref})
        validated.append(ref)
        capabilities.append(_capability(name, available=ref.row_count > 0, required=False))
    return validated, capabilities


def _capability(name: str, *, available: bool, required: bool) -> dict[str, Any]:
    return {
        "capability": name,
        "artifact_name": name,
        "status": "AVAILABLE" if available else "UNAVAILABLE_UPSTREAM",
        "reason": None if available else "artifact absent or contains zero records",
        "required": required,
    }


def validate_phase2_handoff(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    schema_root: Any,
    output_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    require_inputs(inputs, list(REQUIRED_ARTIFACTS) + ["phase4_handoff_manifest"])
    required, by_name = _validate_required(inputs, context, schema_root)
    manifest = _validate_manifest(
        inputs["phase4_handoff_manifest"], context, schema_root, required, by_name
    )
    quality = _quality_gate(
        materialized_mapping(inputs["quality_report_phase_2"], "quality_report_phase_2"), context
    )
    extensions, capabilities = _validate_extensions(inputs, context, schema_root, manifest, required)
    bundle = build_artifact(
        name="validated_phase2_bundle", module_id="P4.S1.M01", context=context,
        records=[ref.to_dict() for ref in required + extensions],
        schema=output_schemas["validated_phase2_bundle"],
        extra={"source_manifest_id": str(manifest.get("handoff_id") or manifest.get("artifact_id")),
               "quality_status": quality},
    )
    capability = build_artifact(
        name="phase2_capability_matrix", module_id="P4.S1.M01", context=context,
        records=capabilities, schema=output_schemas["phase2_capability_matrix"],
    )
    return {"validated_phase2_bundle": bundle, "phase2_capability_matrix": capability}
