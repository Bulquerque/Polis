from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ..errors import BoundaryContractError, BoundaryErrorCode
from ..models import ExecutionContext
from ..runtime.artifacts import materialized_mapping, require_inputs
from ..runtime.canonical import deterministic_id
from ..runtime.datetime_utils import parse_aware_datetime, utc_z
from ..runtime.forbidden import assert_reference_only_manifest, scan_fields
from ..runtime.outputs import build_artifact
from ..runtime.schema_validation import validate_json_schema

REFERENCE_FIELDS = (
    "canonical_society_state_ref",
    "social_feature_ref",
    "context_memory_feature_ref",
    "hypothesis_registry_ref",
    "belief_commitment_ref",
)


def register_variable_evolution(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    output_schema: Mapping[str, Any],
    boundary_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Register an N+1 proposal without applying it to the current cycle."""
    require_inputs(inputs, ["validated_p4_boundary_bundle"])
    boundary = materialized_mapping(
        inputs["validated_p4_boundary_bundle"],
        "validated_p4_boundary_bundle",
    )
    validate_json_schema(boundary, boundary_schema, "validated_p4_boundary_bundle")
    _validate_boundary_identity(boundary, context)
    manifest_value = inputs.get("variable_evolution_input_manifest")
    if manifest_value is None:
        return _empty_registry(context, output_schema)

    manifest = _validated_manifest(manifest_value)
    source_cycle = _validated_source_cycle(context)
    source_as_of = _validated_source_as_of(manifest, context)
    record = _proposal_record(manifest, context, source_cycle, source_as_of)
    return build_artifact(
        name="observer_change_proposal_registry",
        module_id="P4.S1.M04",
        context=context,
        records=[record],
        schema=output_schema,
        extra={"registry_status": "PROPOSAL_REGISTERED"},
    )


def _validate_boundary_identity(
    boundary: Mapping[str, Any],
    context: ExecutionContext,
) -> None:
    expected = {
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": utc_z(context.as_of_time),
        "pipeline_version": context.pipeline_version,
    }
    for field, expected_value in expected.items():
        if str(boundary.get(field)) != expected_value:
            raise BoundaryContractError(
                BoundaryErrorCode.MANIFEST_MISMATCH,
                f"expected {expected_value!r}, got {boundary.get(field)!r}",
                path=f"validated_p4_boundary_bundle.{field}",
            )


def _empty_registry(
    context: ExecutionContext,
    output_schema: Mapping[str, Any],
) -> dict[str, Any]:
    return build_artifact(
        name="observer_change_proposal_registry",
        module_id="P4.S1.M04",
        context=context,
        records=[],
        schema=output_schema,
        extra={"registry_status": "NO_PROPOSAL"},
    )


def _validated_manifest(value: Any) -> Mapping[str, Any]:
    manifest = materialized_mapping(value, "variable_evolution_input_manifest")
    scan_fields(manifest, private=True, path="variable_evolution_input_manifest")
    assert_reference_only_manifest(manifest, "variable_evolution_input_manifest")
    required_fields = ("manifest_id", "as_of_time", "lineage_id", *REFERENCE_FIELDS)
    missing = [field for field in required_fields if not manifest.get(field)]
    if missing:
        raise BoundaryContractError(
            BoundaryErrorCode.SCHEMA_INVALID,
            f"missing fields {missing}",
            path="variable_evolution_input_manifest",
        )
    return manifest


def _validated_source_cycle(context: ExecutionContext) -> str:
    source_cycle = context.variable_evolution_source_cycle_id
    if source_cycle is None:
        raise BoundaryContractError(
            BoundaryErrorCode.N_PLUS_1_BINDING_MISSING,
            "source cycle must be explicitly supplied by the orchestrator",
        )
    if source_cycle == context.cycle_id:
        raise BoundaryContractError(
            BoundaryErrorCode.N_PLUS_1_SAME_CYCLE,
            "same-cycle proposal is forbidden",
        )
    if source_cycle not in context.prior_cycle_ids:
        raise BoundaryContractError(
            BoundaryErrorCode.N_PLUS_1_NOT_PRIOR,
            f"source cycle {source_cycle!r} is not in the authorized prior cycle set",
        )
    return source_cycle


def _validated_source_as_of(
    manifest: Mapping[str, Any],
    context: ExecutionContext,
) -> datetime:
    source_as_of = parse_aware_datetime(
        manifest["as_of_time"],
        "variable_evolution_input_manifest.as_of_time",
    )
    if source_as_of >= context.as_of_time:
        raise BoundaryContractError(
            BoundaryErrorCode.N_PLUS_1_NOT_PRIOR,
            "proposal as_of_time must be strictly earlier than current as_of_time",
        )
    return source_as_of


def _proposal_record(
    manifest: Mapping[str, Any],
    context: ExecutionContext,
    source_cycle: str,
    source_as_of: datetime,
) -> dict[str, Any]:
    references = {field: str(manifest[field]) for field in REFERENCE_FIELDS}
    identity = {
        "manifest_id": manifest["manifest_id"],
        "source_cycle": source_cycle,
        "target_cycle": context.cycle_id,
        "references": references,
    }
    return {
        "proposal_id": deterministic_id("observer-change-proposal", identity),
        "source_manifest_id": str(manifest["manifest_id"]),
        "source_cycle_id": source_cycle,
        "target_cycle_id": context.cycle_id,
        "status": "PENDING_REVIEW",
        "as_of_time": utc_z(source_as_of),
        "references": references,
        "lineage_id": deterministic_id(
            "lineage-observer-change-proposal",
            identity,
            24,
        ),
    }
