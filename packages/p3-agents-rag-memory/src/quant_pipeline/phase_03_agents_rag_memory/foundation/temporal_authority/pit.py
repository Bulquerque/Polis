from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from .canonical import (
    compatibility_sha256,
    ensure_mapping,
    extract_records,
    format_utc,
    parse_aware_datetime,
    record_identity,
    require_no_forbidden_fields,
    stable_sha256,
)
from .errors import Issue, S2ContractError
from .models import (
    EvaluationWindow,
    ExecutionProfile,
    S2Settings,
    TemporalDecision,
    TemporalEvidenceClass,
    ValidationStatus,
)
from .ports import ArtifactResolverPort
from .field_policy import canonical_as_of, coordinates
from .schemas import SchemaRegistry

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _RecordEvaluation:
    temporal_record: dict[str, Any]
    decision: TemporalDecision
    available_at: datetime | None
    issue: Issue | None = None


@dataclass(frozen=True, slots=True)
class _ArtifactEvaluation:
    view: dict[str, Any]
    temporal_records: tuple[dict[str, Any], ...]
    issues: tuple[Issue, ...]
    accepted_count: int
    rejected_future_count: int
    missing_temporal_count: int


def _log_event(event: str, **fields: Any) -> None:
    LOGGER.info(event, extra={"event": event, **fields})


def _evaluation_window(value: Any) -> EvaluationWindow:
    config = ensure_mapping(value, "evaluation_window_config")
    as_of_raw = canonical_as_of(config)
    timezone_name = str(config.get("timezone", "UTC"))
    if timezone_name.upper() != "UTC":
        raise S2ContractError(
            "P3_S2_M01_TIMEZONE_POLICY_INVALID",
            "Internal evaluation timezone must be UTC",
        )
    boundary_rule = str(config.get("boundary_rule", "available_at_equal_as_of_allowed"))
    if boundary_rule != "available_at_equal_as_of_allowed":
        raise S2ContractError(
            "P3_S2_M01_BOUNDARY_POLICY_INVALID",
            f"Unsupported boundary_rule: {boundary_rule}",
        )

    def optional(name: str) -> datetime | None:
        raw = config.get(name)
        return None if raw in (None, "") else parse_aware_datetime(raw, field=name)

    window = EvaluationWindow(
        as_of=parse_aware_datetime(as_of_raw, field="as_of_time"),
        evaluation_start=optional("evaluation_start"),
        evaluation_end=optional("evaluation_end"),
        warmup_start=optional("warmup_start"),
        warmup_end=optional("warmup_end"),
        timezone="UTC",
        boundary_rule=boundary_rule,
    )
    if (
        window.evaluation_start is not None
        and window.evaluation_end is not None
        and window.evaluation_start > window.evaluation_end
    ):
        raise S2ContractError(
            "P3_S2_M01_EVALUATION_WINDOW_INVALID",
            "evaluation_start cannot be after evaluation_end",
        )
    if (
        window.warmup_end is not None
        and window.evaluation_start is not None
        and window.warmup_end >= window.evaluation_start
    ):
        raise S2ContractError(
            "P3_S2_M01_WARMUP_OVERLAPS_EVALUATION",
            "warmup_end must be strictly before evaluation_start",
        )
    return window


def _resolver(config: dict[str, Any]) -> ArtifactResolverPort:
    resolver = config.get("artifact_resolver")
    if resolver is None or not callable(getattr(resolver, "resolve", None)):
        raise S2ContractError(
            "P3_S2_M01_ARTIFACT_RESOLVER_MISSING",
            "An explicit ArtifactResolverPort is required",
        )
    return resolver


def _quality_index(value: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in value.get("quality_decisions", []):
        if not isinstance(row, dict):
            raise S2ContractError(
                "P3_S2_M01_QUALITY_DECISION_INVALID",
                "quality_decisions must contain mappings",
            )
        key = (str(row.get("artifact_name")), str(row.get("record_id")))
        if key in index:
            raise S2ContractError(
                "P3_S2_M01_QUALITY_DECISION_DUPLICATE",
                f"Duplicate quality decision for {key}",
            )
        index[key] = row
    return index


def _temporal_coordinates(
    row: dict[str, Any],
    artifact: dict[str, Any],
    artifact_name: str,
    settings: S2Settings,
) -> tuple[datetime | None, datetime | None, datetime | None, datetime | None, TemporalEvidenceClass]:
    resolved=coordinates(row,artifact,artifact_name,settings.execution_profile)
    evidence = TemporalEvidenceClass.RECORD_LEVEL if row.get("available_at") not in (None,"") else (TemporalEvidenceClass.ARTIFACT_LEVEL if resolved.available_at is not None else TemporalEvidenceClass.MISSING)
    return resolved.event_time,resolved.effective_time,resolved.available_at,resolved.ingested_at,evidence


def _missing_temporal_decision(
    *,
    settings: S2Settings,
    artifact_name: str,
    record_id: str,
) -> tuple[TemporalDecision, Issue]:
    must_block = (
        settings.execution_profile is ExecutionProfile.QUALIFICATION
        and settings.qualification_blocks_missing_available_at
    ) or not settings.development_quarantines_missing_available_at
    if must_block:
        raise S2ContractError(
            "P3_S2_M01_AVAILABLE_AT_MISSING",
            f"Missing temporal evidence for {artifact_name}/{record_id}",
        )
    return (
        TemporalDecision.QUARANTINED_MISSING_TEMPORAL,
        Issue(
            code="P3_S2_M01_AVAILABLE_AT_MISSING",
            severity="WARNING",
            message="Record quarantined because available_at is unavailable",
            artifact_name=artifact_name,
            record_id=record_id,
            field="available_at",
        ),
    )


def _future_record_decision(
    *,
    settings: S2Settings,
    artifact_name: str,
    record_id: str,
) -> tuple[TemporalDecision, Issue]:
    if settings.block_on_future_record:
        raise S2ContractError(
            "P3_S2_M01_AVAILABLE_AT_AFTER_AS_OF",
            f"{artifact_name}/{record_id} became available after as_of",
        )
    return (
        TemporalDecision.REJECTED_FUTURE,
        Issue(
            code="P3_S2_M01_AVAILABLE_AT_AFTER_AS_OF",
            severity="ERROR",
            message="Future record rejected by the point-in-time gate",
            artifact_name=artifact_name,
            record_id=record_id,
            field="available_at",
        ),
    )


def _evaluate_record(
    *,
    row: dict[str, Any],
    index: int,
    artifact: dict[str, Any],
    artifact_name: str,
    artifact_id: str,
    quality_row: dict[str, Any],
    settings: S2Settings,
    window: EvaluationWindow,
) -> _RecordEvaluation:
    record_id = record_identity(row, index)
    event_time, effective_time, available_at, ingested_at, evidence_class = _temporal_coordinates(row, artifact, artifact_name, settings)
    issue: Issue | None = None
    if available_at is None:
        decision, issue = _missing_temporal_decision(
            settings=settings,
            artifact_name=artifact_name,
            record_id=record_id,
        )
    elif available_at > window.as_of:
        decision, issue = _future_record_decision(
            settings=settings,
            artifact_name=artifact_name,
            record_id=record_id,
        )
    else:
        decision = TemporalDecision.ACCEPTED

    temporal_record = {
        "artifact_name": artifact_name,
        "artifact_id": artifact_id,
        "record_id": record_id,
        "source_id": None if row.get("source_id") is None else str(row["source_id"]),
        "event_time": format_utc(event_time),
        "effective_time": format_utc(effective_time),
        "available_at": format_utc(available_at),
        "ingested_at": format_utc(ingested_at),
        "temporal_evidence_class": evidence_class.value,
        "decision": decision.value,
        "quality_decision": str(quality_row["decision"]),
    }
    return _RecordEvaluation(
        temporal_record=temporal_record,
        decision=decision,
        available_at=available_at,
        issue=issue,
    )


def _resolve_artifact(
    *,
    reference: dict[str, Any],
    resolver: ArtifactResolverPort,
    settings: S2Settings,
) -> tuple[str, dict[str, Any], str]:
    artifact_name = str(reference["artifact_name"])
    materialized = ensure_mapping(resolver.resolve(reference), artifact_name)
    require_no_forbidden_fields(materialized, artifact_name)
    observed_hash = compatibility_sha256(materialized)
    if settings.strict_artifact_hashes and observed_hash != reference["content_hash"]:
        raise S2ContractError(
            "P3_S2_M01_ARTIFACT_HASH_MISMATCH",
            f"{artifact_name} hash differs from the S1 reference",
        )
    return artifact_name, materialized, observed_hash


def _evaluate_artifact(
    *,
    reference: dict[str, Any],
    resolver: ArtifactResolverPort,
    quality: dict[tuple[str, str], dict[str, Any]],
    settings: S2Settings,
    window: EvaluationWindow,
) -> _ArtifactEvaluation:
    artifact_name, materialized, observed_hash = _resolve_artifact(
        reference=reference,
        resolver=resolver,
        settings=settings,
    )
    accepted_ids: list[str] = []
    rejected_ids: list[str] = []
    quarantined_ids: list[str] = []
    available_values: list[datetime] = []
    temporal_records: list[dict[str, Any]] = []
    issues: list[Issue] = []

    for index, row in enumerate(extract_records(materialized, artifact_name)):
        record_id = record_identity(row, index)
        quality_row = quality.get((artifact_name, record_id))
        if quality_row is None:
            raise S2ContractError(
                "P3_S2_M01_QUALITY_DECISION_MISSING",
                f"No S1 quality decision for {artifact_name}/{record_id}",
            )
        if not str(quality_row["decision"]).startswith("ACCEPTED"):
            continue
        result = _evaluate_record(
            row=row,
            index=index,
            artifact=materialized,
            artifact_name=artifact_name,
            artifact_id=str(reference["artifact_id"]),
            quality_row=quality_row,
            settings=settings,
            window=window,
        )
        temporal_records.append(result.temporal_record)
        if result.issue is not None:
            issues.append(result.issue)
        if result.decision is TemporalDecision.ACCEPTED:
            accepted_ids.append(record_id)
            if result.available_at is not None:
                available_values.append(result.available_at)
        elif result.decision is TemporalDecision.REJECTED_FUTURE:
            rejected_ids.append(record_id)
        else:
            quarantined_ids.append(record_id)

    view = {
        "source_artifact_ref": dict(reference),
        "observed_content_hash": observed_hash,
        "accepted_record_ids": sorted(accepted_ids),
        "rejected_future_record_ids": sorted(rejected_ids),
        "quarantined_missing_temporal_record_ids": sorted(quarantined_ids),
        "accepted_count": len(accepted_ids),
        "rejected_future_count": len(rejected_ids),
        "missing_temporal_count": len(quarantined_ids),
        "available_at_min": format_utc(min(available_values)) if available_values else None,
        "available_at_max": format_utc(max(available_values)) if available_values else None,
    }
    return _ArtifactEvaluation(
        view=view,
        temporal_records=tuple(temporal_records),
        issues=tuple(issues),
        accepted_count=len(accepted_ids),
        rejected_future_count=len(rejected_ids),
        missing_temporal_count=len(quarantined_ids),
    )


def _build_output(
    *,
    validated: dict[str, Any],
    window: EvaluationWindow,
    evaluations: list[_ArtifactEvaluation],
) -> dict[str, Any]:
    temporal_records = [record for item in evaluations for record in item.temporal_records]
    issues = [issue for item in evaluations for issue in item.issues]
    accepted_total = sum(item.accepted_count for item in evaluations)
    rejected_future_total = sum(item.rejected_future_count for item in evaluations)
    missing_temporal_total = sum(item.missing_temporal_count for item in evaluations)
    status = ValidationStatus.DEGRADED if issues else ValidationStatus.READY
    output: dict[str, Any] = {
        "schema_version": "v14.1-rc4.1",
        "contract_version": "p3.s2.pit_validated_context.v2",
        "validation_status": status.value,
        "run_temporal_boundary": {
            "as_of": format_utc(window.as_of),
            "as_of_time": format_utc(window.as_of),
            "evaluation_start": format_utc(window.evaluation_start),
            "evaluation_end": format_utc(window.evaluation_end),
            "warmup_start": format_utc(window.warmup_start),
            "warmup_end": format_utc(window.warmup_end),
            "timezone": window.timezone,
            "boundary_rule": window.boundary_rule,
        },
        "source_validated_context_hash": str(validated["content_hash"]),
        "artifact_views": [item.view for item in evaluations],
        "temporal_records": sorted(
            temporal_records,
            key=lambda row: (row["artifact_name"], row["record_id"]),
        ),
        "summary": {
            "accepted": accepted_total,
            "rejected_future": rejected_future_total,
            "missing_temporal": missing_temporal_total,
            "total_considered": len(temporal_records),
        },
        "issues": [issue.to_dict() for issue in issues],
        "lineage_id": f"lineage-p3-s2-pit-{stable_sha256(temporal_records)[:20]}",
    }
    output["content_hash"] = stable_sha256(output)
    return output


def apply_point_in_time_gate(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize accepted S1 artifacts and enforce ``available_at <= as_of``."""

    config = config or {}
    settings = S2Settings.from_mapping(config)
    registry = SchemaRegistry()
    immutable_copy = deepcopy(inputs)
    _log_event("module_started", module_id="P3.S2.M01")

    missing = [
        name
        for name in ("validated_context_inputs", "evaluation_window_config")
        if name not in inputs
    ]
    if missing:
        raise S2ContractError(
            "P3_S2_M01_REQUIRED_INPUT_MISSING",
            f"Missing inputs: {missing}",
        )
    validated = ensure_mapping(inputs["validated_context_inputs"], "validated_context_inputs")
    registry.validate_dependency("validated_context_inputs", validated)
    require_no_forbidden_fields(validated, "validated_context_inputs")
    window = _evaluation_window(inputs["evaluation_window_config"])
    resolver = _resolver(config)
    quality = _quality_index(validated)

    evaluations = [
        _evaluate_artifact(
            reference=reference,
            resolver=resolver,
            quality=quality,
            settings=settings,
            window=window,
        )
        for reference in sorted(
            validated["source_artifacts"],
            key=lambda row: row["artifact_name"],
        )
        if str(reference["artifact_name"]) != "source_quality_panel"
    ]
    if inputs != immutable_copy:
        raise S2ContractError(
            "P3_S2_INPUT_MUTATION_DETECTED",
            "P3.S2.M01 mutated its inputs",
        )

    output = _build_output(validated=validated, window=window, evaluations=evaluations)
    registry.validate_internal("pit_validated_context", output)
    require_no_forbidden_fields(output, "pit_validated_context")
    summary = output["summary"]
    _log_event(
        "module_succeeded",
        module_id="P3.S2.M01",
        validation_status=output["validation_status"],
        input_record_count=summary["total_considered"],
        output_record_count=summary["accepted"],
        warning_count=len(output["issues"]),
        error_count=summary["rejected_future"],
    )
    return output
