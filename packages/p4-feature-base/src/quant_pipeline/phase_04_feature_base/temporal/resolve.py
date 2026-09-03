from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import CompatibilityMode, ExecutionContext
from ..runtime.canonical import canonical_value, deterministic_id
from ..runtime.datetime_utils import utc_z
from .errors import TemporalContractError, TemporalErrorCode
from .materialization import materialized_sources, validate_s1_outputs
from .output import build_s2_artifact
from .policy import ArtifactPolicy, policy_for
from .time import ResolvedInstant, optional_instant, resolve_instant


def _first(row: Mapping[str, Any], fields: tuple[str, ...]) -> tuple[str | None, Any]:
    for field in fields:
        if row.get(field) not in (None, ""):
            return field, row[field]
    return None, None


def _timezone(row: Mapping[str, Any], policy: ArtifactPolicy) -> str:
    _, value = _first(row, policy.timezone_fields)
    return str(value) if value not in (None, "") else policy.default_timezone

def _fold(row: Mapping[str, Any]) -> int | None:
    value = row.get("fold")
    if value is None:
        return None
    if value not in (0, 1, "0", "1"):
        raise TemporalContractError(
            TemporalErrorCode.TEMPORAL_VALUE_INVALID,
            "fold must be 0 or 1",
            path="record.fold",
        )
    return int(value)


def _optional(
    row: Mapping[str, Any],
    fields: tuple[str, ...],
    *,
    policy: ArtifactPolicy,
    path: str,
    date_only_policy: str,
) -> tuple[str | None, ResolvedInstant | None]:
    field, value = _first(row, fields)
    if field is None:
        return None, None
    return field, optional_instant(
        value,
        path=f"{path}.{field}",
        timezone_name=_timezone(row, policy),
        date_only_policy=date_only_policy,
        fold=_fold(row),
    )


def _compatibility_availability(
    source_created_at: str,
    policy: ArtifactPolicy,
    context: ExecutionContext,
    path: str,
) -> tuple[str, Any, list[str]]:
    allowed = (
        policy.allow_created_at_availability_fallback
        and context.compatibility_mode is CompatibilityMode.RC4_1
    )
    if not allowed:
        raise TemporalContractError(
            TemporalErrorCode.TEMPORAL_VALUE_MISSING,
            "available_at is required by the artifact policy",
            path=path,
        )
    created = resolve_instant(
        source_created_at,
        path=f"{path}.artifact.created_at",
        timezone_name=policy.default_timezone,
        date_only_policy=policy.date_only_available_policy,
    )
    if created.value <= context.decision_time:
        return (
            "artifact.created_at",
            source_created_at,
            ["available_at resolved conservatively from artifact.created_at"],
        )
    warning = (
        "legacy record has no available_at and artifact.created_at is after decision_time; "
        "compatibility uses decision_time as an unknown-availability ceiling"
    )
    return "compatibility.decision_time_ceiling", utc_z(context.decision_time), [warning]


def _validate_availability(
    instant: ResolvedInstant,
    context: ExecutionContext,
    path: str,
) -> None:
    if instant.value > context.decision_time:
        raise TemporalContractError(
            TemporalErrorCode.FUTURE_AVAILABILITY,
            "available_at is after decision_time",
            path=path,
            details={
                "available_at": instant.utc_text(),
                "decision_time": utc_z(context.decision_time),
            },
        )
    if instant.value > context.as_of_time:
        raise TemporalContractError(
            TemporalErrorCode.FUTURE_AVAILABILITY,
            "available_at is after as_of_time",
            path=path,
        )


def _available(
    row: Mapping[str, Any],
    source_created_at: str,
    policy: ArtifactPolicy,
    context: ExecutionContext,
    path: str,
) -> tuple[ResolvedInstant, str, tuple[str, ...]]:
    field, value = _first(row, policy.available_fields)
    warnings: list[str] = []
    if field is None:
        field, value, warnings = _compatibility_availability(
            source_created_at, policy, context, path
        )
    instant = resolve_instant(
        value,
        path=f"{path}.{field}",
        timezone_name=_timezone(row, policy),
        date_only_policy=policy.date_only_available_policy,
        fold=_fold(row),
    )
    _validate_availability(instant, context, f"{path}.{field}")
    return instant, field, tuple(warnings)



def _record_decision_time(
    row: Mapping[str, Any],
    available: ResolvedInstant,
    policy: ArtifactPolicy,
    context: ExecutionContext,
    path: str,
) -> ResolvedInstant:
    """Resolve an optional per-record decision time for historical backfills.

    Snapshot runs continue to use ``context.decision_time``. Backfill producers may
    provide ``decision_time`` on every record; it must be no earlier than the
    information availability time and no later than the run cutoff.
    """
    raw = row.get("decision_time")
    if raw in (None, ""):
        return resolve_instant(
            utc_z(context.decision_time),
            path=f"{path}.context.decision_time",
            timezone_name="UTC",
            date_only_policy="START_OF_DAY",
        )
    instant = resolve_instant(
        raw,
        path=f"{path}.decision_time",
        timezone_name=_timezone(row, policy),
        date_only_policy=policy.date_only_available_policy,
        fold=_fold(row),
    )
    if instant.value < available.value:
        raise TemporalContractError(
            TemporalErrorCode.FUTURE_AVAILABILITY,
            "available_at is after the record decision_time",
            path=f"{path}.decision_time",
            details={
                "available_at": available.utc_text(),
                "decision_time": instant.utc_text(),
            },
        )
    if instant.value > context.decision_time or instant.value > context.as_of_time:
        raise TemporalContractError(
            TemporalErrorCode.FUTURE_AVAILABILITY,
            "record decision_time is after the run cutoff",
            path=f"{path}.decision_time",
            details={
                "record_decision_time": instant.utc_text(),
                "run_decision_time": utc_z(context.decision_time),
                "run_as_of_time": utc_z(context.as_of_time),
            },
        )
    return instant

def _vintage(row: Mapping[str, Any]) -> str | None:
    for field in ("vintage_id", "revision_id", "realtime_start", "vintage_date"):
        if row.get(field) not in (None, ""):
            return str(row[field])
    return None


def _resolved_times(
    row: Mapping[str, Any],
    policy: ArtifactPolicy,
    path: str,
) -> dict[str, tuple[str | None, ResolvedInstant | None]]:
    requests = {
        "reference": (policy.reference_fields, policy.date_only_reference_policy),
        "event": (policy.event_fields, policy.date_only_event_policy),
        "published": (policy.published_fields, policy.date_only_event_policy),
        "ingested": (policy.ingested_fields, policy.date_only_event_policy),
    }
    return {
        name: _optional(
            row,
            fields,
            policy=policy,
            path=path,
            date_only_policy=date_only_policy,
        )
        for name, (fields, date_only_policy) in requests.items()
    }


def _time_fields(
    resolved: Mapping[str, tuple[str | None, ResolvedInstant | None]]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, (field, instant) in resolved.items():
        target = "published_at" if name == "published" else f"{name}_time"
        if name == "ingested":
            target = "ingested_at"
        result[target] = instant.utc_text() if instant else None
        result[f"{target}_source"] = field
        if name in {"event", "reference"}:
            result[f"{target}_precision"] = instant.precision if instant else None
    return result


def _resolve_record(
    *,
    artifact_name: str,
    artifact_id: str,
    artifact_lineage_id: str,
    source_created_at: str,
    index: int,
    row: Mapping[str, Any],
    context: ExecutionContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = policy_for(artifact_name)
    path = f"{artifact_name}.records[{index}]"
    available, availability_source, warnings = _available(
        row, source_created_at, policy, context, path
    )
    record_decision = _record_decision_time(row, available, policy, context, path)
    resolved = _resolved_times(row, policy, path)
    payload = canonical_value(dict(row))
    source_record_id = deterministic_id(
        "source-record",
        {"artifact_id": artifact_id, "index": index, "payload": payload},
        24,
    )
    record = {
        "source_record_id": source_record_id,
        "source_artifact_name": artifact_name,
        "source_artifact_id": artifact_id,
        "source_record_index": index,
        "source_modality": policy.modality,
        "entity_type_hint": policy.entity_type,
        **_time_fields(resolved),
        "available_at": available.utc_text(),
        "available_at_source": availability_source,
        "decision_time": record_decision.utc_text(),
        "calculation_time": utc_z(context.created_at),
        "original_timezone": available.original_timezone,
        "vintage_id": _vintage(row),
        "stable_sequence": row.get("stable_sequence") or row.get("sequence_id"),
        "source_lineage_id": str(row.get("lineage_id") or artifact_lineage_id),
        "temporal_status": "DEGRADED" if warnings else "VALIDATED",
        "warnings": list(warnings),
        "payload": payload,
    }
    report = {
        "source_record_id": source_record_id,
        "artifact_name": artifact_name,
        "status": record["temporal_status"],
        "available_at": available.utc_text(),
        "availability_resolution": availability_source,
        "warnings": list(warnings),
    }
    return record, report


def _resolve_sources(
    inputs: Mapping[str, Any], context: ExecutionContext
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for source in materialized_sources(inputs):
        for index, row in enumerate(source.records):
            resolved, entry = _resolve_record(
                artifact_name=source.artifact_name,
                artifact_id=source.artifact_id,
                artifact_lineage_id=source.lineage_id,
                source_created_at=source.created_at,
                index=index,
                row=row,
                context=context,
            )
            records.append(resolved)
            report.append(entry)
    records.sort(
        key=lambda row: (
            row["available_at"],
            row["source_artifact_name"],
            row["source_record_id"],
        )
    )
    report.sort(key=lambda row: (row["artifact_name"], row["source_record_id"]))
    return records, report


def resolve_temporal_semantics(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    s1_schemas: Mapping[str, Mapping[str, Any]],
    s2_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    validate_s1_outputs(inputs, s1_schemas, context)
    records, report = _resolve_sources(inputs, context)
    bundle = build_s2_artifact(
        name="temporally_resolved_observation_bundle",
        module_id="P4.S2.M01",
        context=context,
        records=records,
        schema=s2_schemas["temporally_resolved_observation_bundle"],
        extra={"temporal_policy_version": "p4.s2.temporal.v1"},
    )
    resolution_report = build_s2_artifact(
        name="temporal_resolution_report",
        module_id="P4.S2.M01",
        context=context,
        records=report,
        schema=s2_schemas["temporal_resolution_report"],
    )
    return {
        "temporally_resolved_observation_bundle": bundle,
        "temporal_resolution_report": resolution_report,
    }
