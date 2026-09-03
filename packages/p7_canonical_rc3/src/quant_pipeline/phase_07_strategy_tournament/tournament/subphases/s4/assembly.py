from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope
from ...boundary.input_records import ParetoFrontierRecord
from ...boundary.output_records import (
    AppliedPenalty,
    CandidatePolicyResolution,
    HeadScoreContribution,
    InterpretableScoreRecord,
    ScoringHeadRecord,
    ScoringPolicyReceiptRecord,
)
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity
from ...domain.enums import HeadStatus, MissingHeadAction, ScoreStatus
from ...domain.errors import ContractViolation, InternalInvariantViolation
from .artifact_support import build_outputs, output_lineage, unique_by

MODULE_ID = "P7.S4.M03"
REQUIRED = ("scoring_head_panel", "scoring_policy_receipt", "pareto_frontier_panel")


@dataclass(frozen=True, slots=True)
class AssemblyInputs:
    heads: ArtifactEnvelope[ScoringHeadRecord]
    receipt: ArtifactEnvelope[ScoringPolicyReceiptRecord]
    pareto: ArtifactEnvelope[ParetoFrontierRecord]

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        return (self.heads, self.receipt, self.pareto)


def _parse(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> AssemblyInputs:
    require_inputs(inputs, REQUIRED, MODULE_ID)
    kwargs = {"module_id": MODULE_ID, "strict_hash_validation": config.strict_hash_validation}
    parsed = AssemblyInputs(
        heads=parse_artifact(inputs["scoring_head_panel"], ScoringHeadRecord, expected_name="scoring_head_panel", **kwargs),
        receipt=parse_artifact(inputs["scoring_policy_receipt"], ScoringPolicyReceiptRecord, expected_name="scoring_policy_receipt", **kwargs),
        pareto=parse_artifact(inputs["pareto_frontier_panel"], ParetoFrontierRecord, expected_name="pareto_frontier_panel", **kwargs),
    )
    validate_common_identity(parsed.artifacts(), module_id=MODULE_ID)
    if len(parsed.receipt.records) != 1:
        raise ContractViolation("P7_S4_RECEIPT_RECORD_COUNT_INVALID", "scoring receipt must contain one record", module_id=MODULE_ID)
    return parsed


def _usable_head(record: ScoringHeadRecord) -> bool:
    return record.head_score is not None and record.head_status in {
        HeadStatus.AVAILABLE,
        HeadStatus.PENALIZED,
        HeadStatus.RENORMALIZED,
    }


def _resolve_head_value(record: ScoringHeadRecord) -> tuple[float | None, str | None]:
    if _usable_head(record):
        return record.head_score, None
    if record.missing_head_action == MissingHeadAction.BLOCK:
        return None, "P7_S4_SCORE_BLOCKED_MISSING_HEAD"
    if record.missing_head_action == MissingHeadAction.PENALIZE:
        return record.missing_head_penalty, "P7_S4_HEAD_MISSING_PENALTY_APPLIED"
    return None, "P7_S4_HEAD_RENORMALIZED_AWAY"



def _collect_head_values(
    resolution: CandidatePolicyResolution,
    heads: dict[str, ScoringHeadRecord],
) -> tuple[list[HeadScoreContribution], dict[str, float], str | None]:
    contributions: list[HeadScoreContribution] = []
    values: dict[str, float] = {}
    for head_id in resolution.head_ids:
        record = heads.get(head_id)
        if record is None:
            return contributions, values, "P7_S4_EXPECTED_HEAD_RECORD_MISSING"
        value, reason = _resolve_head_value(record)
        if value is None and record.missing_head_action == MissingHeadAction.BLOCK:
            return contributions, values, reason
        if value is None:
            continue
        values[head_id] = value
        contributions.append(
            HeadScoreContribution(
                head_id=head_id,
                head_score=value,
                head_weight=record.head_weight,
                weighted_contribution=0.0,
                source_status=record.head_status,
            )
        )
    return contributions, values, None


def _normalize_head_contributions(
    contributions: list[HeadScoreContribution],
) -> tuple[tuple[HeadScoreContribution, ...], float]:
    total_weight = sum(row.head_weight for row in contributions)
    normalized = tuple(
        row.model_copy(update={"weighted_contribution": row.head_score * row.head_weight / total_weight})
        for row in contributions
    )
    return normalized, total_weight


def _penalties(resolution: CandidatePolicyResolution, values: dict[str, float]) -> tuple[AppliedPenalty, ...]:
    return tuple(
        AppliedPenalty(
            penalty_id=rule.penalty_id,
            head_id=rule.head_id,
            threshold=rule.threshold,
            coefficient=rule.coefficient,
            head_score=values[rule.head_id],
            penalty_value=rule.coefficient * max(0.0, rule.threshold - values[rule.head_id]),
        )
        for rule in resolution.penalty_rules
        if rule.head_id in values
    )


def _assemble_candidate(
    resolution: CandidatePolicyResolution,
    heads: dict[str, ScoringHeadRecord],
    policy_id: str,
    policy_version: str,
    tolerance: float,
) -> InterpretableScoreRecord:
    contributions, values, blocked_reason = _collect_head_values(resolution, heads)
    if blocked_reason is not None:
        return _blocked_record(resolution, policy_id, policy_version, blocked_reason)
    total_weight = sum(row.head_weight for row in contributions)
    if total_weight <= 0.0:
        return _blocked_record(resolution, policy_id, policy_version, "P7_S4_SCORE_NO_USABLE_HEADS", unavailable=True)
    normalized, total_weight = _normalize_head_contributions(contributions)
    base_score = sum(row.weighted_contribution for row in normalized)
    penalties = _penalties(resolution, values)
    penalty_total = sum(row.penalty_value for row in penalties)
    confidence_score = values.get(resolution.confidence_head_id) if resolution.confidence_head_id else None
    if resolution.confidence_shrinkage_strength > 0.0 and confidence_score is None:
        return _blocked_record(resolution, policy_id, policy_version, "P7_S4_CONFIDENCE_HEAD_UNAVAILABLE", unavailable=True)
    confidence_adjustment = 0.0 if confidence_score is None else -resolution.confidence_shrinkage_strength * (1.0 - confidence_score) * base_score
    pre_boundary_score = base_score - penalty_total + confidence_adjustment
    final_score = max(0.0, min(1.0, pre_boundary_score))
    boundary_adjustment = final_score - pre_boundary_score
    if abs(sum(row.weighted_contribution for row in normalized) - base_score) > tolerance:
        raise InternalInvariantViolation("P7_S4_HEAD_CONSERVATION_FAILED", "head contributions do not reconcile", module_id=MODULE_ID)
    return InterpretableScoreRecord(
        candidate_id=resolution.candidate_id,
        comparison_group_id=resolution.comparison_group_id,
        policy_id=policy_id,
        policy_version=policy_version,
        rule_id=resolution.rule_id,
        score_status=ScoreStatus.AVAILABLE,
        base_score=base_score,
        effective_head_weight=total_weight,
        head_contributions=normalized,
        applied_penalties=penalties,
        penalty_total=penalty_total,
        confidence_head_id=resolution.confidence_head_id,
        confidence_score=confidence_score,
        confidence_adjustment=confidence_adjustment,
        boundary_adjustment=boundary_adjustment,
        final_interpretable_score=final_score,
        reason_code=None,
        lineage_id=heads[next(iter(heads))].lineage_id,
    )

def _blocked_record(
    resolution: CandidatePolicyResolution,
    policy_id: str,
    policy_version: str,
    reason: str,
    *,
    unavailable: bool = False,
) -> InterpretableScoreRecord:
    return InterpretableScoreRecord(
        candidate_id=resolution.candidate_id,
        comparison_group_id=resolution.comparison_group_id,
        policy_id=policy_id,
        policy_version=policy_version,
        rule_id=resolution.rule_id,
        score_status=ScoreStatus.UNAVAILABLE if unavailable else ScoreStatus.BLOCKED,
        base_score=None,
        effective_head_weight=0.0,
        head_contributions=(),
        applied_penalties=(),
        penalty_total=0.0,
        confidence_head_id=resolution.confidence_head_id,
        confidence_score=None,
        confidence_adjustment=0.0,
        boundary_adjustment=0.0,
        final_interpretable_score=None,
        reason_code=reason,
        lineage_id=f"unavailable:{resolution.candidate_id}",
    )


def assemble_interpretable_scores(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse(inputs, config)
    receipt = parsed.receipt.records[0]
    unique_by(parsed.pareto.records, lambda row: row.candidate_id, code="P7_S4_DUPLICATE_PARETO_CANDIDATE", module_id=MODULE_ID)
    grouped: dict[str, dict[str, ScoringHeadRecord]] = defaultdict(dict)
    for record in parsed.heads.records:
        if record.head_id in grouped[record.candidate_id]:
            raise ContractViolation("P7_S4_DUPLICATE_HEAD_RECORD", "duplicate candidate-head record", module_id=MODULE_ID)
        grouped[record.candidate_id][record.head_id] = record
    records = tuple(
        _assemble_candidate(
            resolution,
            grouped.get(resolution.candidate_id, {}),
            receipt.policy_id,
            receipt.policy_version,
            config.numerical_tolerance,
        )
        for resolution in receipt.resolutions
    )
    lineage = output_lineage(MODULE_ID, parsed.artifacts())
    return build_outputs(
        module_id=MODULE_ID,
        base=parsed.heads,
        execution_time=config.execution_time,
        lineage_id=lineage,
        named_records={"interpretable_score_panel": tuple(sorted(records, key=lambda row: (row.comparison_group_id, row.candidate_id)))},
    )
