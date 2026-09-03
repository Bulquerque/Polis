from __future__ import annotations

from collections.abc import Iterable

from ...boundary.input_records import FactorExposureRecord
from ...boundary.output_records import InterpretableScoreRecord, ScoreDecompositionRecord, ScoringHeadRecord
from ...domain.enums import ComponentType


def _head_row(
    score: InterpretableScoreRecord,
    head: ScoringHeadRecord,
    contribution: float,
    global_weight: float,
    artifact_ids: dict[str, str],
) -> ScoreDecompositionRecord:
    return ScoreDecompositionRecord(
        candidate_id=score.candidate_id,
        comparison_group_id=score.comparison_group_id,
        stage_type=ComponentType.HEAD,
        stage_id=f"head:{head.head_id}",
        head_id=head.head_id,
        metric_id=None,
        raw_value=head.head_score,
        transformed_value=None,
        normalized_value=head.head_score,
        local_weight=head.head_weight,
        global_weight=global_weight,
        score_contribution=contribution,
        source_artifact_id=artifact_ids["scoring_head_panel"],
        policy_id=score.policy_id,
        policy_version=score.policy_version,
        lineage_id=score.lineage_id,
    )


def _metric_rows(
    score: InterpretableScoreRecord,
    head: ScoringHeadRecord,
    head_global_weight: float,
    artifact_ids: dict[str, str],
) -> list[ScoreDecompositionRecord]:
    rows: list[ScoreDecompositionRecord] = []
    for stage in head.stages:
        available = stage.normalized_value is not None and head.effective_metric_weight > 0.0
        global_weight = None if not available else head_global_weight * stage.metric_weight / head.effective_metric_weight
        contribution = 0.0 if global_weight is None else stage.normalized_value * global_weight
        rows.append(
            ScoreDecompositionRecord(
                candidate_id=score.candidate_id,
                comparison_group_id=score.comparison_group_id,
                stage_type=ComponentType.METRIC,
                stage_id=f"metric:{head.head_id}:{stage.metric_id}",
                head_id=head.head_id,
                metric_id=stage.metric_id,
                raw_value=stage.raw_directed_value,
                transformed_value=stage.transformed_value,
                normalized_value=stage.normalized_value,
                local_weight=stage.metric_weight,
                global_weight=global_weight,
                score_contribution=contribution,
                source_artifact_id=artifact_ids["comparable_candidate_metric_panel"],
                policy_id=score.policy_id,
                policy_version=score.policy_version,
                lineage_id=score.lineage_id,
            )
        )
    return rows


def _adjustment_rows(score: InterpretableScoreRecord, artifact_ids: dict[str, str]) -> list[ScoreDecompositionRecord]:
    rows = [
        ScoreDecompositionRecord(
            candidate_id=score.candidate_id,
            comparison_group_id=score.comparison_group_id,
            stage_type=ComponentType.PENALTY,
            stage_id=f"penalty:{penalty.penalty_id}",
            head_id=penalty.head_id,
            metric_id=None,
            raw_value=penalty.head_score,
            transformed_value=penalty.threshold,
            normalized_value=None,
            local_weight=penalty.coefficient,
            global_weight=None,
            score_contribution=-penalty.penalty_value,
            source_artifact_id=artifact_ids["interpretable_score_panel"],
            policy_id=score.policy_id,
            policy_version=score.policy_version,
            lineage_id=score.lineage_id,
        )
        for penalty in score.applied_penalties
    ]
    if score.confidence_head_id is not None:
        rows.append(
            ScoreDecompositionRecord(
                candidate_id=score.candidate_id,
                comparison_group_id=score.comparison_group_id,
                stage_type=ComponentType.CONFIDENCE,
                stage_id="confidence_adjustment",
                head_id=score.confidence_head_id,
                metric_id=None,
                raw_value=score.confidence_score,
                transformed_value=None,
                normalized_value=score.confidence_score,
                local_weight=None,
                global_weight=None,
                score_contribution=score.confidence_adjustment,
                source_artifact_id=artifact_ids["interpretable_score_panel"],
                policy_id=score.policy_id,
                policy_version=score.policy_version,
                lineage_id=score.lineage_id,
            )
        )
    return rows



def _boundary_row(score: InterpretableScoreRecord, artifact_ids: dict[str, str]) -> ScoreDecompositionRecord | None:
    if score.boundary_adjustment == 0.0:
        return None
    return ScoreDecompositionRecord(
        candidate_id=score.candidate_id,
        comparison_group_id=score.comparison_group_id,
        stage_type=ComponentType.BOUNDARY,
        stage_id="boundary_adjustment",
        head_id=None,
        metric_id=None,
        raw_value=score.base_score - score.penalty_total + score.confidence_adjustment if score.base_score is not None else None,
        transformed_value=score.final_interpretable_score,
        normalized_value=score.final_interpretable_score,
        local_weight=None,
        global_weight=None,
        score_contribution=score.boundary_adjustment,
        source_artifact_id=artifact_ids["interpretable_score_panel"],
        policy_id=score.policy_id,
        policy_version=score.policy_version,
        lineage_id=score.lineage_id,
    )

def decompose_score(
    score: InterpretableScoreRecord,
    heads: dict[tuple[str, str], ScoringHeadRecord],
    artifact_ids: dict[str, str],
) -> tuple[ScoreDecompositionRecord, ...]:
    rows: list[ScoreDecompositionRecord] = []
    for contribution in score.head_contributions:
        head = heads[(score.candidate_id, contribution.head_id)]
        global_weight = contribution.head_weight / score.effective_head_weight
        rows.append(_head_row(score, head, contribution.weighted_contribution, global_weight, artifact_ids))
        rows.extend(_metric_rows(score, head, global_weight, artifact_ids))
    rows.extend(_adjustment_rows(score, artifact_ids))
    boundary = _boundary_row(score, artifact_ids)
    if boundary is not None:
        rows.append(boundary)
    return tuple(rows)


def factor_rows(
    exposures: Iterable[FactorExposureRecord],
    scored_ids: set[str],
    policy_id: str,
    policy_version: str,
    artifact_id: str,
) -> tuple[ScoreDecompositionRecord, ...]:
    return tuple(
        ScoreDecompositionRecord(
            candidate_id=row.candidate_id,
            comparison_group_id=row.comparison_group_id,
            stage_type=ComponentType.FACTOR,
            stage_id=f"factor:{row.factor_id}",
            head_id="ECONOMIC_EDGE",
            metric_id=None,
            raw_value=row.exposure_value,
            transformed_value=row.contribution,
            normalized_value=None,
            local_weight=row.coefficient,
            global_weight=None,
            score_contribution=0.0,
            source_artifact_id=artifact_id,
            policy_id=policy_id,
            policy_version=policy_version,
            lineage_id=row.lineage_id,
        )
        for row in sorted(exposures, key=lambda item: (item.comparison_group_id, item.candidate_id, item.factor_id))
        if row.candidate_id in scored_ids
    )
