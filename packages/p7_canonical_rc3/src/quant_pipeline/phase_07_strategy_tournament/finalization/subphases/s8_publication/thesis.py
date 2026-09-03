"""Build evidence-bound thesis cards, traces and audit inputs."""
from __future__ import annotations

from dataclasses import dataclass

from ...boundary.s8_config import RankingPolicy, ThesisPolicy
from ...boundary.s8_inputs import ScoreDecompositionRecord
from ...boundary.s8_outputs import RankedStrategyRecord, RankingTraceRecord, SortComponent, ThesisCardRecord
from ...boundary.inputs import StrategyReferenceRecord


@dataclass(frozen=True, slots=True)
class ThesisOutputs:
    cards: tuple[ThesisCardRecord, ...]
    traces: tuple[RankingTraceRecord, ...]


def _availability(strategy: StrategyReferenceRecord, contributions: dict[str, float]) -> dict[str, str]:
    return {
        "belief_references": "AVAILABLE" if strategy.belief_reference_ids else "UNAVAILABLE",
        "origin_and_mutations": "AVAILABLE" if strategy.origin_template or strategy.mutation_trace else "UNAVAILABLE",
        "payoff_shape": "AVAILABLE" if strategy.payoff_shape else "UNAVAILABLE",
        "profit_regions": "AVAILABLE" if strategy.profit_regions else "UNAVAILABLE",
        "failure_regions": "AVAILABLE" if strategy.failure_regions else "UNAVAILABLE",
        "score_contributions": "AVAILABLE" if contributions else "UNAVAILABLE",
        "invalidation_conditions": "AVAILABLE" if strategy.invalidation_conditions else "UNAVAILABLE",
    }


def _nearest_alternatives(
    ranked: tuple[RankedStrategyRecord, ...], item: RankedStrategyRecord, limit: int
) -> tuple[str, ...]:
    candidates = [
        other for other in ranked
        if other.candidate_id != item.candidate_id
        and other.comparison_group_id == item.comparison_group_id
        and other.diversity_cluster_id == item.diversity_cluster_id
    ]
    candidates.sort(key=lambda row: (row.rank_position, row.candidate_id))
    return tuple(row.candidate_id for row in candidates[:limit])


def _sort_stages(item: RankedStrategyRecord) -> tuple[SortComponent, ...]:
    return (
        SortComponent(name="pareto_tier", value=item.pareto_tier, direction="ASC"),
        SortComponent(name="diversity_adjusted_score", value=item.diversity_adjusted_score, direction="DESC"),
        SortComponent(name="score_confidence", value=item.score_confidence, direction="DESC"),
        SortComponent(name="robustness_stage", value=item.robustness_stage, direction="DESC"),
        SortComponent(name="execution_quality_stage", value=item.execution_quality_stage, direction="DESC"),
        SortComponent(name="leg_count", value=item.leg_count, direction="ASC"),
        SortComponent(name="candidate_id", value=item.candidate_id, direction="ASC"),
    )


def build_thesis_outputs(
    ranked: tuple[RankedStrategyRecord, ...],
    strategies: dict[str, StrategyReferenceRecord],
    decomposition: dict[str, tuple[ScoreDecompositionRecord, ...]],
    ranking_policy: RankingPolicy,
    thesis_policy: ThesisPolicy,
    evidence_artifact_ids: tuple[str, ...],
) -> ThesisOutputs:
    cards: list[ThesisCardRecord] = []
    traces: list[RankingTraceRecord] = []
    for item in sorted(ranked, key=lambda row: (row.comparison_group_id, row.rank_position)):
        strategy = strategies[item.candidate_id]
        contributions = {row.head: row.contribution for row in decomposition.get(item.candidate_id, ())}
        cards.append(ThesisCardRecord(
            cycle_id=item.cycle_id,
            decision_time=item.decision_time,
            comparison_group_id=item.comparison_group_id,
            candidate_id=item.candidate_id,
            rank_position=item.rank_position,
            belief_reference_ids=strategy.belief_reference_ids,
            objective_family=item.objective_family,
            origin_template=strategy.origin_template,
            mutation_trace=strategy.mutation_trace,
            payoff_shape_reference=f"{strategy.strategy_artifact_id}#payoff_shape",
            profit_regions=strategy.profit_regions,
            failure_regions=strategy.failure_regions,
            score_contributions=contributions,
            confidence_state={
                "score_confidence": item.score_confidence,
                "calibration_status": item.calibration_status,
                "calibration_version": item.calibration_version,
                "model_disagreement": item.model_disagreement,
            },
            ood_state=item.ood_severity,
            nearest_alternative_ids=_nearest_alternatives(ranked, item, thesis_policy.max_nearest_alternatives),
            invalidation_conditions=strategy.invalidation_conditions,
            section_availability=_availability(strategy, contributions),
            evidence_artifact_ids=evidence_artifact_ids,
            policy_version=thesis_policy.policy_id,
            lineage_id=item.lineage_id,
        ))
        traces.append(RankingTraceRecord(
            cycle_id=item.cycle_id,
            decision_time=item.decision_time,
            comparison_group_id=item.comparison_group_id,
            candidate_id=item.candidate_id,
            rank_position=item.rank_position,
            sort_stages=_sort_stages(item),
            economic_tie_id=item.economic_tie_id,
            policy_versions={"ranking": ranking_policy.policy_id, "thesis": thesis_policy.policy_id},
            model_id=item.model_id,
            evidence_artifact_ids=evidence_artifact_ids,
            lineage_id=item.lineage_id,
        ))
    return ThesisOutputs(tuple(cards), tuple(traces))
