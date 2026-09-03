from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..models import ExecutionContext
from ..runtime.artifacts import materialized_mapping
from ..runtime.canonical import content_hash
from ..runtime.schema_validation import validate_json_schema
from .errors import TemporalContractError, TemporalErrorCode

_REQUIRED_S1 = (
    "validated_p4_boundary_bundle",
    "validated_phase2_bundle",
    "validated_phase3_bundle",
    "phase2_capability_matrix",
    "phase3_capability_matrix",
)


@dataclass(frozen=True, slots=True)
class MaterializedSource:
    artifact_name: str
    artifact_id: str
    lineage_id: str
    created_at: str
    records: tuple[Mapping[str, Any], ...]
    artifact: Mapping[str, Any]


def require_s1_outputs(inputs: Mapping[str, Any]) -> None:
    missing = [name for name in _REQUIRED_S1 if name not in inputs]
    if missing:
        raise TemporalContractError(
            TemporalErrorCode.INPUT_MISSING,
            f"missing S1 outputs: {missing}",
            path="inputs",
        )


def validate_s1_outputs(
    inputs: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
    context: ExecutionContext,
) -> None:
    require_s1_outputs(inputs)
    for name in _REQUIRED_S1:
        artifact = materialized_mapping(inputs[name], name)
        try:
            validate_json_schema(artifact, schemas[name], name)
        except Exception as exc:
            raise TemporalContractError(
                TemporalErrorCode.SCHEMA_INVALID,
                str(exc),
                path=name,
            ) from exc
        for field, expected in (
            ("run_id", context.run_id),
            ("cycle_id", context.cycle_id),
            ("pipeline_version", context.pipeline_version),
        ):
            if str(artifact.get(field)) != expected:
                raise TemporalContractError(
                    TemporalErrorCode.BOUNDARY_REFERENCE_MISMATCH,
                    f"expected {expected!r}, got {artifact.get(field)!r}",
                    path=f"{name}.{field}",
                )


def _reference_map(bundle: Mapping[str, Any], name: str) -> dict[str, Mapping[str, Any]]:
    records = bundle.get("records", [])
    if not isinstance(records, list):
        raise TemporalContractError(
            TemporalErrorCode.INPUT_INVALID,
            "bundle records must be a list",
            path=f"{name}.records",
        )
    result: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or not record.get("artifact_name"):
            raise TemporalContractError(
                TemporalErrorCode.INPUT_INVALID,
                "invalid artifact reference",
                path=f"{name}.records[{index}]",
            )
        artifact_name = str(record["artifact_name"])
        if artifact_name in result:
            raise TemporalContractError(
                TemporalErrorCode.INPUT_INVALID,
                f"duplicate artifact reference {artifact_name!r}",
                path=f"{name}.records[{index}]",
            )
        result[artifact_name] = record
    return result


def materialized_sources(inputs: Mapping[str, Any]) -> list[MaterializedSource]:
    refs: dict[str, Mapping[str, Any]] = {}
    for bundle_name in ("validated_phase2_bundle", "validated_phase3_bundle"):
        bundle = materialized_mapping(inputs[bundle_name], bundle_name)
        refs.update(_reference_map(bundle, bundle_name))
    result: list[MaterializedSource] = []
    for artifact_name in sorted(refs):
        if artifact_name == "quality_report_phase_2":
            continue
        if artifact_name not in inputs:
            raise TemporalContractError(
                TemporalErrorCode.INPUT_MISSING,
                "validated artifact payload is not materialized",
                path=artifact_name,
            )
        artifact = materialized_mapping(inputs[artifact_name], artifact_name)
        ref = refs[artifact_name]
        if str(artifact.get("artifact_id")) != str(ref.get("artifact_id")):
            raise TemporalContractError(
                TemporalErrorCode.BOUNDARY_REFERENCE_MISMATCH,
                "artifact_id differs from the validated S1 reference",
                path=f"{artifact_name}.artifact_id",
            )
        computed = content_hash(artifact)
        if str(ref.get("content_hash")) != computed:
            raise TemporalContractError(
                TemporalErrorCode.BOUNDARY_REFERENCE_MISMATCH,
                "content hash differs from the validated S1 reference",
                path=f"{artifact_name}.content_hash",
            )
        records = artifact.get("records", [])
        if records is None:
            records = []
        if not isinstance(records, list) or any(not isinstance(row, Mapping) for row in records):
            raise TemporalContractError(
                TemporalErrorCode.INPUT_INVALID,
                "records must be a list of mappings",
                path=f"{artifact_name}.records",
            )
        result.append(
            MaterializedSource(
                artifact_name=artifact_name,
                artifact_id=str(artifact["artifact_id"]),
                lineage_id=str(artifact["lineage_id"]),
                created_at=str(artifact["created_at"]),
                records=tuple(records),
                artifact=artifact,
            )
        )
    return result


def capability_records(inputs: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for name in ("phase2_capability_matrix", "phase3_capability_matrix"):
        artifact = materialized_mapping(inputs[name], name)
        rows = artifact.get("records", [])
        if isinstance(rows, list):
            result.extend(row for row in rows if isinstance(row, Mapping))
    return result
