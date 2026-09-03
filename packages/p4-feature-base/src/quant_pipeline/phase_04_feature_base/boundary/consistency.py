from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import BoundaryContractError, BoundaryErrorCode
from ..models import ExecutionContext
from ..runtime.artifacts import materialized_mapping, require_inputs
from ..runtime.datetime_utils import utc_z
from ..runtime.outputs import build_artifact
from ..runtime.schema_validation import validate_json_schema

_P3_UNIVERSE_ARTIFACTS = (
    "social_feature_panel",
    "evidence_tag_panel",
    "agent_disagreement_panel",
    "context_memory_feature_panel",
)


def _artifact_names(bundle: Mapping[str, Any]) -> set[str]:
    records = bundle.get("records", [])
    if not isinstance(records, list):
        raise BoundaryContractError(BoundaryErrorCode.SCHEMA_INVALID, "bundle records must be a list")
    return {str(record.get("artifact_name")) for record in records if isinstance(record, Mapping)}


def _underlying_universe(raw_inputs: Mapping[str, Any], artifact_name: str) -> set[str]:
    artifact = raw_inputs.get(artifact_name)
    if not isinstance(artifact, Mapping):
        return set()
    records = artifact.get("records", [])
    if not isinstance(records, list):
        return set()
    values = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        value = record.get("underlying") or record.get("underlying_id") or record.get("entity_id")
        if value:
            values.add(str(value))
    return values


def _expected_context_value(context: ExecutionContext, field: str) -> str:
    if field == "as_of_time":
        return utc_z(context.as_of_time)
    return str(getattr(context, field))


def _bundle_reference(source_phase: str, bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_phase": source_phase,
        "bundle_artifact_id": str(bundle["artifact_id"]),
        "manifest_artifact_id": str(bundle["source_manifest_id"]),
        "artifact_count": len(_artifact_names(bundle)),
    }


def _validate_bundle_identity(
    p2: Mapping[str, Any],
    p3: Mapping[str, Any],
    context: ExecutionContext,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    error_codes = {
        "run_id": BoundaryErrorCode.RUN_MISMATCH,
        "cycle_id": BoundaryErrorCode.CYCLE_MISMATCH,
        "as_of_time": BoundaryErrorCode.AS_OF_MISMATCH,
        "pipeline_version": BoundaryErrorCode.PIPELINE_VERSION_MISMATCH,
    }
    for field, code in error_codes.items():
        expected = _expected_context_value(context, field)
        values = {str(p2.get(field)), str(p3.get(field))}
        if values != {expected}:
            raise BoundaryContractError(
                code,
                f"bundle {field} values {sorted(values)} do not equal {expected!r}",
            )
        checks.append({"check": field, "status": "PASS", "details": {"value": expected}})
    return checks


def _validate_universe(
    raw_inputs: Mapping[str, Any],
) -> tuple[set[str], dict[str, Any]]:
    p2_universe = _underlying_universe(raw_inputs, "clean_underlying_panel")
    p3_universe: set[str] = set()
    for name in _P3_UNIVERSE_ARTIFACTS:
        p3_universe.update(_underlying_universe(raw_inputs, name))
    unknown = p3_universe - p2_universe
    if unknown:
        raise BoundaryContractError(
            BoundaryErrorCode.UNIVERSE_MISMATCH,
            f"P3 contains underlyings absent from P2: {sorted(unknown)}",
        )
    details = {
        "p2_size": len(p2_universe),
        "p3_size": len(p3_universe),
        "p3_subset_of_p2": True,
    }
    return p2_universe, {"check": "universe", "status": "PASS", "details": details}


def validate_boundary_consistency(
    inputs: Mapping[str, Any],
    raw_inputs: Mapping[str, Any],
    context: ExecutionContext,
    output_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    require_inputs(inputs, ["validated_phase2_bundle", "validated_phase3_bundle"])
    p2 = materialized_mapping(inputs["validated_phase2_bundle"], "validated_phase2_bundle")
    p3 = materialized_mapping(inputs["validated_phase3_bundle"], "validated_phase3_bundle")
    validate_json_schema(
        p2,
        output_schemas["validated_phase2_bundle"],
        "validated_phase2_bundle",
    )
    validate_json_schema(
        p3,
        output_schemas["validated_phase3_bundle"],
        "validated_phase3_bundle",
    )
    checks = _validate_bundle_identity(p2, p3, context)
    p2_universe, universe_check = _validate_universe(raw_inputs)
    checks.append(universe_check)
    refs = [_bundle_reference("P2", p2), _bundle_reference("P3", p3)]
    capabilities = {
        "P2": sorted(_artifact_names(p2)),
        "P3": sorted(_artifact_names(p3)),
    }
    boundary = build_artifact(
        name="validated_p4_boundary_bundle",
        module_id="P4.S1.M03",
        context=context,
        records=refs,
        schema=output_schemas["validated_p4_boundary_bundle"],
        extra={
            "universe": sorted(p2_universe),
            "identity_sources": {
                "run": "execution_context",
                "cycle": "execution_context",
                "as_of": "execution_context",
            },
            "capabilities": capabilities,
        },
    )
    report = build_artifact(
        name="boundary_consistency_report",
        module_id="P4.S1.M03",
        context=context,
        records=checks,
        schema=output_schemas["boundary_consistency_report"],
    )
    return {
        "validated_p4_boundary_bundle": boundary,
        "boundary_consistency_report": report,
    }
