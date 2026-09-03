from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..errors import BoundaryContractError, BoundaryErrorCode
from ..models import ArtifactReference, CompatibilityMode, ExecutionContext
from .canonical import content_hash, p2_legacy_digest
from .datetime_utils import parse_aware_datetime, utc_z
from .forbidden import scan_fields
from .schema_validation import load_schema, validate_legacy_upstream_schema
from .yaml_loader import TextResource


# Upstream packages keep their own release versions.  Compatibility mode may
# accept only these known boundary versions; arbitrary version drift remains a
# hard failure.
_KNOWN_UPSTREAM_PIPELINE_VERSIONS = frozenset({"V14.1-RC4.1", "p3-live-mini"})


def is_compatible_upstream_pipeline(
    pipeline_version: str, context: ExecutionContext
) -> bool:
    return (
        context.compatibility_mode is CompatibilityMode.RC4_1
        and pipeline_version in _KNOWN_UPSTREAM_PIPELINE_VERSIONS
    )


def require_inputs(inputs: Mapping[str, Any], names: list[str] | tuple[str, ...]) -> None:
    missing = [name for name in names if name not in inputs]
    if missing:
        raise BoundaryContractError(
            BoundaryErrorCode.INPUT_MISSING, f"missing inputs: {missing}", path="inputs"
        )


def materialized_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BoundaryContractError(
            BoundaryErrorCode.INPUT_NOT_MATERIALIZED, "artifact must be a mapping", path=name
        )
    if value.get("source") or value.get("synthesized"):
        raise BoundaryContractError(
            BoundaryErrorCode.INPUT_NOT_MATERIALIZED, "source placeholders are forbidden", path=name
        )
    return value


def _top_level_metadata(artifact: Mapping[str, Any], name: str) -> tuple[str, str, str, str]:
    missing = [field for field in ("artifact_id", "lineage_id", "pipeline_version") if not artifact.get(field)]
    if missing:
        raise BoundaryContractError(
            BoundaryErrorCode.INPUT_NOT_MATERIALIZED, f"missing metadata {missing}", path=name
        )
    created = artifact.get("created_at")
    if created is None:
        raise BoundaryContractError(
            BoundaryErrorCode.INPUT_NOT_MATERIALIZED, "created_at is required", path=name
        )
    parse_aware_datetime(created, f"{name}.created_at")
    return (
        str(artifact["artifact_id"]), str(artifact["lineage_id"]),
        str(artifact["pipeline_version"]), str(created),
    )


def _validate_declared_identity(
    artifact: Mapping[str, Any],
    name: str,
    context: ExecutionContext,
) -> None:
    expected = {
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": utc_z(context.as_of_time),
    }
    codes = {
        "run_id": BoundaryErrorCode.RUN_MISMATCH,
        "cycle_id": BoundaryErrorCode.CYCLE_MISMATCH,
        "as_of_time": BoundaryErrorCode.AS_OF_MISMATCH,
    }
    for field, expected_value in expected.items():
        declared = artifact.get(field)
        if declared is None:
            continue
        actual = (
            utc_z(parse_aware_datetime(declared, f"{name}.{field}"))
            if field == "as_of_time"
            else str(declared)
        )
        if actual != expected_value:
            raise BoundaryContractError(
                codes[field],
                f"expected {expected_value!r}, got {actual!r}",
                path=f"{name}.{field}",
            )


def _schema_metadata_and_warnings(
    name: str,
    artifact: Mapping[str, Any],
    schema_path: str | Path | TextResource | None,
    context: ExecutionContext,
) -> tuple[str | None, tuple[str, ...]]:
    schema_version = artifact.get("schema_version")
    if schema_path is None:
        return (str(schema_version) if schema_version is not None else None, ())
    is_file = (
        Path(schema_path).is_file()
        if isinstance(schema_path, (str, Path))
        else schema_path.is_file()
    )
    if not is_file:
        message = f"compatibility schema unavailable for {name}"
        if context.compatibility_mode is CompatibilityMode.STRICT:
            raise BoundaryContractError(
                BoundaryErrorCode.SCHEMA_INVALID,
                message,
                path=name,
            )
        return (
            str(schema_version) if schema_version is not None else None,
            (message,),
        )
    schema = load_schema(schema_path)
    warnings = validate_legacy_upstream_schema(
        name, artifact, schema, context.compatibility_mode
    )
    resolved_version = schema_version or schema.get("schema_version")
    return (
        str(resolved_version) if resolved_version is not None else None,
        warnings,
    )


def validate_artifact(
    name: str,
    value: Any,
    *,
    context: ExecutionContext,
    schema_path: str | Path | TextResource | None,
    private_scan: bool,
    compatibility_hash: str | None,
) -> ArtifactReference:
    artifact = materialized_mapping(value, name)
    scan_fields(artifact, private=private_scan, path=name)
    artifact_id, lineage_id, pipeline_version, _ = _top_level_metadata(artifact, name)
    _validate_declared_identity(artifact, name, context)
    version_warning: tuple[str, ...] = ()
    if pipeline_version != context.pipeline_version:
        if is_compatible_upstream_pipeline(pipeline_version, context):
            version_warning = (
                f"upstream pipeline version {pipeline_version!r} accepted by explicit RC4_1 compatibility",
            )
        else:
            raise BoundaryContractError(
                BoundaryErrorCode.PIPELINE_VERSION_MISMATCH,
                f"expected {context.pipeline_version!r}, got {pipeline_version!r}",
                path=f"{name}.pipeline_version",
            )
    records = artifact.get("records", [])
    if records is None:
        records = []
    if not isinstance(records, list):
        raise BoundaryContractError(
            BoundaryErrorCode.INPUT_NOT_MATERIALIZED,
            "records must be a list",
            path=f"{name}.records",
        )
    schema_version, warnings = _schema_metadata_and_warnings(
        name, artifact, schema_path, context
    )
    warnings = (*version_warning, *warnings)
    schema_id = artifact.get("schema_id")
    canonical = content_hash(artifact)
    legacy = p2_legacy_digest(artifact) if compatibility_hash == "P2" else None
    quality = str(
        artifact.get("quality_status") or artifact.get("status") or "LEGACY_UNVERIFIED"
    ).upper()
    compatibility = "STRICT" if not warnings else "LEGACY_COMPATIBLE_WITH_WARNINGS"
    return ArtifactReference(
        artifact_name=name,
        artifact_id=artifact_id,
        schema_id=str(schema_id) if schema_id is not None else None,
        schema_version=schema_version,
        content_hash=canonical,
        legacy_content_hash=legacy,
        lineage_id=lineage_id,
        row_count=len(records),
        quality_status=quality,
        compatibility_status=compatibility,
        warnings=warnings,
    )
