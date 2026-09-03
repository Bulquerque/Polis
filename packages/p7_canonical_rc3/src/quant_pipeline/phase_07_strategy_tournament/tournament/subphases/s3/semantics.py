from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.records import (
    ComparisonGroupRecord,
    ComparableMetricRecord,
    EligibleCandidateRecord,
    FoundationAuditRecord,
    HandoffManifestRecord,
    MetricPolicy,
    MetricSemanticsAuditRecord,
    MetricSourceRecord,
    RankingPolicyRecord,
)
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity, validate_manifest_references
from ...domain.enums import ComparisonStatus, Direction, MissingAction, MissingnessStatus
from ...domain.errors import ContractViolation, TemporalViolation
from ...domain.forbidden import scan_forbidden_fields
from .artifact_support import build_outputs, output_lineage, reason_counts, single_policy, unique_by

MODULE_ID = "P7.S3.M01"
REQUIRED_INPUTS = (
    "runtime_foundation_handoff_manifest",
    "eligible_strategy_candidate_panel",
    "candidate_comparison_group_panel",
    "candidate_metric_source_panel",
    "ranking_policy_context",
    "runtime_foundation_audit_report",
)


@dataclass(frozen=True, slots=True)
class SemanticsInputs:
    manifest: ArtifactEnvelope[HandoffManifestRecord]
    candidates: ArtifactEnvelope[EligibleCandidateRecord]
    groups: ArtifactEnvelope[ComparisonGroupRecord]
    metrics: ArtifactEnvelope[MetricSourceRecord]
    policy_artifact: ArtifactEnvelope[RankingPolicyRecord]
    foundation_audit: ArtifactEnvelope[FoundationAuditRecord]

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        return (
            self.manifest,
            self.candidates,
            self.groups,
            self.metrics,
            self.policy_artifact,
            self.foundation_audit,
        )


def _parse_inputs(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> SemanticsInputs:
    require_inputs(inputs, REQUIRED_INPUTS, MODULE_ID)
    types = (
        HandoffManifestRecord,
        EligibleCandidateRecord,
        ComparisonGroupRecord,
        MetricSourceRecord,
        RankingPolicyRecord,
        FoundationAuditRecord,
    )
    parsed = [
        parse_artifact(
            inputs[name], record_type, expected_name=name, module_id=MODULE_ID,
            strict_hash_validation=config.strict_hash_validation,
        )
        for name, record_type in zip(REQUIRED_INPUTS, types, strict=True)
    ]
    return SemanticsInputs(*parsed)


def _validate_handoff(parsed: SemanticsInputs, policy: RankingPolicyRecord) -> None:
    artifacts = {artifact.artifact_name: artifact for artifact in parsed.artifacts()[1:]}
    validate_common_identity(parsed.artifacts(), module_id=MODULE_ID)
    validate_manifest_references(
        parsed.manifest,
        artifacts,
        required_names=REQUIRED_INPUTS[1:],
        module_id=MODULE_ID,
    )
    if len(parsed.foundation_audit.records) != 1:
        raise ContractViolation(
            "P7_S3_FOUNDATION_AUDIT_INVALID", "Foundation audit must contain one record", module_id=MODULE_ID
        )
    audit = parsed.foundation_audit.records[0]
    if not audit.comparison_groups_frozen or not audit.candidate_reconciliation_passed:
        raise ContractViolation(
            "P7_S3_FOUNDATION_AUDIT_INVALID", "Foundation foundation was not closed", module_id=MODULE_ID
        )
    scan_forbidden_fields(
        {artifact.artifact_name: artifact.model_dump(mode="json") for artifact in parsed.artifacts()},
        set(policy.forbidden_field_names),
        module_id=MODULE_ID,
    )


def _reconcile_identity(parsed: SemanticsInputs) -> tuple[dict[str, EligibleCandidateRecord], dict[str, ComparisonGroupRecord]]:
    candidate_by_id = unique_by(
        parsed.candidates.records, lambda row: row.candidate_id,
        code="P7_S3_DUPLICATE_CANDIDATE", module_id=MODULE_ID,
    )
    group_by_id = unique_by(
        parsed.groups.records, lambda row: row.candidate_id,
        code="P7_S3_DUPLICATE_GROUP_BINDING", module_id=MODULE_ID,
    )
    if set(candidate_by_id) != set(group_by_id):
        raise ContractViolation(
            "P7_S3_CANDIDATE_GROUP_RECONCILIATION_FAILED",
            "eligible candidates and comparison groups do not reconcile",
            module_id=MODULE_ID,
            details={
                "candidate_only": sorted(set(candidate_by_id) - set(group_by_id)),
                "group_only": sorted(set(group_by_id) - set(candidate_by_id)),
            },
        )
    return candidate_by_id, group_by_id


def _missing_record(
    candidate: EligibleCandidateRecord,
    group: ComparisonGroupRecord,
    metric_policy: MetricPolicy,
    source: ArtifactEnvelope[MetricSourceRecord],
) -> ComparableMetricRecord:
    mapping = {
        MissingAction.BLOCK: (MissingnessStatus.BLOCKED, ComparisonStatus.BLOCKED, "P7_S3_REQUIRED_METRIC_MISSING"),
        MissingAction.UNAVAILABLE: (MissingnessStatus.UNAVAILABLE, ComparisonStatus.UNAVAILABLE, "P7_S3_METRIC_UNAVAILABLE"),
        MissingAction.OPTIONAL: (
            MissingnessStatus.OPTIONAL_MISSING,
            ComparisonStatus.OPTIONAL_MISSING,
            "P7_S3_OPTIONAL_METRIC_MISSING",
        ),
    }
    missingness, comparison, reason = mapping[metric_policy.missing_action]
    return ComparableMetricRecord(
        candidate_id=candidate.candidate_id,
        comparison_group_id=group.comparison_group_id,
        metric_id=metric_policy.metric_id,
        raw_value=None,
        canonical_value=None,
        directed_value=None,
        canonical_units=metric_policy.canonical_units,
        direction=metric_policy.direction,
        semantic_version=metric_policy.semantic_version,
        source_artifact_id=source.artifact_id,
        source_available_at=source.available_at,
        missingness_status=missingness,
        comparison_status=comparison,
        reason_code=reason,
        lineage_id=candidate.lineage_id,
    )


def _available_record(
    source: MetricSourceRecord,
    group: ComparisonGroupRecord,
    metric_policy: MetricPolicy,
    conversions: dict[tuple[str, str, str], tuple[float, float]],
) -> tuple[ComparableMetricRecord, bool]:
    if source.direction != metric_policy.direction or source.semantic_version != metric_policy.semantic_version:
        raise ContractViolation(
            "P7_S3_METRIC_SEMANTICS_MISMATCH",
            "metric direction or semantic version differs from policy",
            module_id=MODULE_ID,
            details={"candidate_id": source.candidate_id, "metric_id": source.metric_id},
        )
    canonical_value = source.raw_value
    converted = False
    if source.units != metric_policy.canonical_units:
        conversion = conversions.get((source.metric_id, source.units, metric_policy.canonical_units))
        if conversion is None:
            raise ContractViolation(
                "P7_S3_UNIT_CONVERSION_NOT_DECLARED",
                "metric units differ and no explicit conversion exists",
                module_id=MODULE_ID,
                details={"candidate_id": source.candidate_id, "metric_id": source.metric_id, "units": source.units},
            )
        factor, offset = conversion
        canonical_value = source.raw_value * factor + offset  # type: ignore[operator]
        converted = True
    directed = canonical_value if metric_policy.direction == Direction.MAXIMIZE else -canonical_value  # type: ignore[operator]
    return ComparableMetricRecord(
        candidate_id=source.candidate_id,
        comparison_group_id=group.comparison_group_id,
        metric_id=source.metric_id,
        raw_value=source.raw_value,
        canonical_value=canonical_value,
        directed_value=directed,
        canonical_units=metric_policy.canonical_units,
        direction=metric_policy.direction,
        semantic_version=metric_policy.semantic_version,
        source_artifact_id=source.source_artifact_id,
        source_available_at=source.available_at,
        missingness_status=MissingnessStatus.AVAILABLE,
        comparison_status=ComparisonStatus.AVAILABLE,
        reason_code=None,
        lineage_id=source.lineage_id,
    ), converted


def _compile_records(
    parsed: SemanticsInputs,
    policy: RankingPolicyRecord,
    candidates: dict[str, EligibleCandidateRecord],
    groups: dict[str, ComparisonGroupRecord],
) -> tuple[tuple[ComparableMetricRecord, ...], int]:
    source_by_grain = unique_by(
        parsed.metrics.records, lambda row: (row.candidate_id, row.metric_id),
        code="P7_S3_DUPLICATE_METRIC_GRAIN", module_id=MODULE_ID,
    )
    unknown = sorted({row.candidate_id for row in parsed.metrics.records} - set(candidates))
    if unknown:
        raise ContractViolation(
            "P7_S3_METRIC_CANDIDATE_UNKNOWN", "metric references unknown candidate",
            module_id=MODULE_ID, details={"candidate_ids": unknown},
        )
    future = [row for row in parsed.metrics.records if row.available_at > parsed.metrics.decision_time]
    if future:
        raise TemporalViolation(
            "P7_S3_METRIC_AVAILABLE_AFTER_DECISION", "metric was not available at decision time",
            module_id=MODULE_ID,
            details={"grains": sorted((row.candidate_id, row.metric_id) for row in future)},
        )
    policy_by_metric = {row.metric_id: row for row in policy.metric_policies}
    conversions = {
        (row.metric_id, row.from_units, row.to_units): (row.factor, row.offset)
        for row in policy.unit_conversions
    }
    output: list[ComparableMetricRecord] = []
    converted_count = 0
    for candidate_id in sorted(candidates):
        for metric_id in sorted(policy_by_metric):
            metric_policy = policy_by_metric[metric_id]
            source = source_by_grain.get((candidate_id, metric_id))
            if source is None or source.missingness_status != MissingnessStatus.AVAILABLE:
                output.append(_missing_record(candidates[candidate_id], groups[candidate_id], metric_policy, parsed.metrics))
                continue
            record, converted = _available_record(source, groups[candidate_id], metric_policy, conversions)
            output.append(record)
            converted_count += converted
    return tuple(sorted(output, key=lambda row: (row.comparison_group_id, row.candidate_id, row.metric_id))), converted_count


def compile_metric_semantics(
    inputs: Mapping[str, Any],
    config: ModuleExecutionConfig,
) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse_inputs(inputs, config)
    policy = single_policy(parsed.policy_artifact, module_id=MODULE_ID)
    _validate_handoff(parsed, policy)
    candidates, groups = _reconcile_identity(parsed)
    records, converted_count = _compile_records(parsed, policy, candidates, groups)
    audit = MetricSemanticsAuditRecord(
        policy_id=policy.policy_id,
        candidate_count=len(candidates),
        source_metric_count=len(parsed.metrics.records),
        output_metric_count=len(records),
        converted_metric_count=converted_count,
        blocked_metric_count=sum(row.comparison_status == ComparisonStatus.BLOCKED for row in records),
        unavailable_metric_count=sum(
            row.comparison_status in {ComparisonStatus.UNAVAILABLE, ComparisonStatus.OPTIONAL_MISSING}
            for row in records
        ),
        forbidden_field_scan_passed=True,
        duplicate_grain_count=0,
        reason_counts=reason_counts(row.reason_code for row in records),
    )
    return build_outputs(
        module_id=MODULE_ID,
        base=parsed.manifest,
        execution_time=config.execution_time,
        lineage_id=output_lineage(MODULE_ID, parsed.artifacts()),
        named_records={"comparable_candidate_metric_panel": records, "metric_semantics_audit_report": (audit,)},
    )
