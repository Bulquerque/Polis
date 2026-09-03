from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope, build_artifact
from ...boundary.input_records import (
    ArtifactReference,
    ComparableMetricRecord,
    DominanceRelationRecord,
    DominanceSurvivorRecord,
    DominatedCandidateRecord,
    FactorAdjustedMetricRecord,
    FactorAdjustmentAuditRecord,
    FactorExposureRecord,
    MetricSemanticsAuditRecord,
    ParetoFrontierAuditRecord,
    ParetoFrontierRecord,
)
from ...boundary.output_records import (
    TournamentHandoffManifestRecord,
    InterpretableScoreRecord,
    InterpretableTournamentAuditRecord,
    ScoreDecompositionRecord,
    ScoringHeadRecord,
    ScoringPolicyReceiptRecord,
)
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity
from ...domain.enums import ComponentType, FrontierStatus, ScoreStatus
from ...domain.errors import ContractViolation, InternalInvariantViolation
from ...domain.forbidden import scan_forbidden_fields
from .artifact_support import build_outputs, output_lineage, unique_by
from .decomposition import decompose_score, factor_rows

MODULE_ID = "P7.S4.M04"
REQUIRED = (
    "interpretable_score_panel",
    "scoring_head_panel",
    "scoring_policy_receipt",
    "pareto_frontier_panel",
    "pareto_frontier_audit_report",
    "dominated_candidate_panel",
    "dominance_survivor_panel",
    "dominance_relation_panel",
    "factor_adjusted_metric_panel",
    "factor_exposure_panel",
    "comparable_candidate_metric_panel",
    "metric_semantics_audit_report",
    "factor_adjustment_audit_report",
)
FORBIDDEN = {
    "future_return", "realized_return", "realized_pnl", "outcome", "target_return",
    "rank", "portfolio_weight", "execution_price", "fill_price",
}


@dataclass(frozen=True, slots=True)
class PublicationInputs:
    scores: ArtifactEnvelope[InterpretableScoreRecord]
    heads: ArtifactEnvelope[ScoringHeadRecord]
    receipt: ArtifactEnvelope[ScoringPolicyReceiptRecord]
    pareto: ArtifactEnvelope[ParetoFrontierRecord]
    pareto_audit: ArtifactEnvelope[ParetoFrontierAuditRecord]
    dominated: ArtifactEnvelope[DominatedCandidateRecord]
    survivors: ArtifactEnvelope[DominanceSurvivorRecord]
    relations: ArtifactEnvelope[DominanceRelationRecord]
    adjusted: ArtifactEnvelope[FactorAdjustedMetricRecord]
    exposures: ArtifactEnvelope[FactorExposureRecord]
    comparable: ArtifactEnvelope[ComparableMetricRecord]
    semantics_audit: ArtifactEnvelope[MetricSemanticsAuditRecord]
    factor_audit: ArtifactEnvelope[FactorAdjustmentAuditRecord]

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        return tuple(getattr(self, field) for field in self.__dataclass_fields__)


def _parse(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> PublicationInputs:
    require_inputs(inputs, REQUIRED, MODULE_ID)
    k = {"module_id": MODULE_ID, "strict_hash_validation": config.strict_hash_validation}
    parsed = PublicationInputs(
        scores=parse_artifact(inputs["interpretable_score_panel"], InterpretableScoreRecord, expected_name="interpretable_score_panel", **k),
        heads=parse_artifact(inputs["scoring_head_panel"], ScoringHeadRecord, expected_name="scoring_head_panel", **k),
        receipt=parse_artifact(inputs["scoring_policy_receipt"], ScoringPolicyReceiptRecord, expected_name="scoring_policy_receipt", **k),
        pareto=parse_artifact(inputs["pareto_frontier_panel"], ParetoFrontierRecord, expected_name="pareto_frontier_panel", **k),
        pareto_audit=parse_artifact(inputs["pareto_frontier_audit_report"], ParetoFrontierAuditRecord, expected_name="pareto_frontier_audit_report", **k),
        dominated=parse_artifact(inputs["dominated_candidate_panel"], DominatedCandidateRecord, expected_name="dominated_candidate_panel", **k),
        survivors=parse_artifact(inputs["dominance_survivor_panel"], DominanceSurvivorRecord, expected_name="dominance_survivor_panel", **k),
        relations=parse_artifact(inputs["dominance_relation_panel"], DominanceRelationRecord, expected_name="dominance_relation_panel", **k),
        adjusted=parse_artifact(inputs["factor_adjusted_metric_panel"], FactorAdjustedMetricRecord, expected_name="factor_adjusted_metric_panel", **k),
        exposures=parse_artifact(inputs["factor_exposure_panel"], FactorExposureRecord, expected_name="factor_exposure_panel", **k),
        comparable=parse_artifact(inputs["comparable_candidate_metric_panel"], ComparableMetricRecord, expected_name="comparable_candidate_metric_panel", **k),
        semantics_audit=parse_artifact(inputs["metric_semantics_audit_report"], MetricSemanticsAuditRecord, expected_name="metric_semantics_audit_report", **k),
        factor_audit=parse_artifact(inputs["factor_adjustment_audit_report"], FactorAdjustmentAuditRecord, expected_name="factor_adjustment_audit_report", **k),
    )
    validate_common_identity(parsed.artifacts(), module_id=MODULE_ID)
    if len(parsed.receipt.records) != 1:
        raise ContractViolation("P7_S4_RECEIPT_RECORD_COUNT_INVALID", "scoring receipt must contain one record", module_id=MODULE_ID)
    scan_forbidden_fields(inputs, FORBIDDEN, module_id=MODULE_ID)
    return parsed



def _reference(artifact: ArtifactEnvelope[Any]) -> ArtifactReference:
    return ArtifactReference(
        artifact_name=artifact.artifact_name,
        artifact_id=artifact.artifact_id,
        content_sha256=artifact.content_sha256,
        schema_version=artifact.schema_version,
        record_count=artifact.record_count,
    )



def _build_audit(
    parsed: PublicationInputs,
    receipt: ScoringPolicyReceiptRecord,
    scores: dict[str, InterpretableScoreRecord],
    frontiers: dict[str, ParetoFrontierRecord],
    decomposition: tuple[ScoreDecompositionRecord, ...],
    max_error: float,
) -> InterpretableTournamentAuditRecord:
    reasons = Counter(row.reason_code for row in scores.values() if row.reason_code)
    return InterpretableTournamentAuditRecord(
        policy_id=receipt.policy_id,
        policy_version=receipt.policy_version,
        input_candidate_count=len(frontiers),
        frontier_candidate_count=sum(row.frontier_status == FrontierStatus.FRONTIER for row in frontiers.values()),
        dominated_candidate_count=len(parsed.dominated.records),
        incomparable_candidate_count=sum(row.frontier_status == FrontierStatus.INCOMPARABLE for row in frontiers.values()),
        scored_candidate_count=sum(row.score_status == ScoreStatus.AVAILABLE for row in scores.values()),
        blocked_candidate_count=sum(row.score_status == ScoreStatus.BLOCKED for row in scores.values()),
        unavailable_candidate_count=sum(row.score_status == ScoreStatus.UNAVAILABLE for row in scores.values()),
        decomposition_record_count=len(decomposition),
        max_abs_reconciliation_error=max_error,
        candidate_conservation_passed=set(scores).issubset(frontiers),
        forbidden_field_scan_passed=True,
        reason_counts=dict(sorted(reasons.items())),
    )


def _reconciliation_error(
    scores: dict[str, InterpretableScoreRecord],
    decomposition: tuple[ScoreDecompositionRecord, ...],
) -> float:
    errors: list[float] = []
    counted = {ComponentType.HEAD, ComponentType.PENALTY, ComponentType.CONFIDENCE, ComponentType.BOUNDARY}
    for score in scores.values():
        if score.final_interpretable_score is None:
            continue
        total = sum(
            row.score_contribution for row in decomposition
            if row.candidate_id == score.candidate_id and row.stage_type in counted
        )
        errors.append(abs(total - score.final_interpretable_score))
    return max(errors, default=0.0)


def _build_manifest(
    parsed: PublicationInputs,
    preliminary: dict[str, ArtifactEnvelope[Any]],
    config: ModuleExecutionConfig,
    lineage: str,
) -> ArtifactEnvelope[Any]:
    references = tuple(_reference(artifact) for artifact in (*parsed.artifacts(), *preliminary.values()))
    record = TournamentHandoffManifestRecord(
        contract_id="p7-tournament-interpretable-tournament-v1",
        producer="P7.TOURNAMENT",
        consumer="P7.LEARNING",
        references=tuple(sorted(references, key=lambda row: row.artifact_name)),
    )
    return build_artifact(
        artifact_name="interpretable_tournament_handoff_manifest",
        schema_version="1.0.0",
        producer_module_id=MODULE_ID,
        run_id=parsed.scores.run_id,
        cycle_id=parsed.scores.cycle_id,
        decision_time=parsed.scores.decision_time,
        execution_time=config.execution_time,
        available_at=max(artifact.available_at for artifact in parsed.artifacts()),
        lineage_id=lineage,
        records=(record,),
    )


def publish_tournament_handoff(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse(inputs, config)
    receipt = parsed.receipt.records[0]
    scores = unique_by(parsed.scores.records, lambda row: row.candidate_id, code="P7_S4_DUPLICATE_SCORE", module_id=MODULE_ID)
    heads = unique_by(parsed.heads.records, lambda row: (row.candidate_id, row.head_id), code="P7_S4_DUPLICATE_HEAD_RECORD", module_id=MODULE_ID)
    frontiers = unique_by(parsed.pareto.records, lambda row: row.candidate_id, code="P7_S4_DUPLICATE_PARETO_CANDIDATE", module_id=MODULE_ID)
    artifact_ids = {artifact.artifact_name: artifact.artifact_id for artifact in parsed.artifacts()}
    decomposition = tuple(row for candidate_id in sorted(scores) for row in decompose_score(scores[candidate_id], heads, artifact_ids))
    decomposition += factor_rows(parsed.exposures.records, set(scores), receipt.policy_id, receipt.policy_version, parsed.exposures.artifact_id)
    max_error = _reconciliation_error(scores, decomposition)
    if max_error > config.numerical_tolerance:
        raise InternalInvariantViolation(
            "P7_S4_DECOMPOSITION_RECONCILIATION_FAILED",
            "decomposition does not reconcile",
            module_id=MODULE_ID,
            details={"max_error": max_error},
        )
    audit = _build_audit(parsed, receipt, scores, frontiers, decomposition, max_error)
    lineage = output_lineage(MODULE_ID, parsed.artifacts())
    preliminary = build_outputs(
        module_id=MODULE_ID,
        base=parsed.scores,
        execution_time=config.execution_time,
        lineage_id=lineage,
        named_records={
            "score_decomposition_panel": tuple(sorted(decomposition, key=lambda row: (row.comparison_group_id, row.candidate_id, row.stage_type, row.stage_id))),
            "interpretable_tournament_audit_report": (audit,),
        },
    )
    manifest = _build_manifest(parsed, preliminary, config, lineage)
    return {**preliminary, "interpretable_tournament_handoff_manifest": manifest}
