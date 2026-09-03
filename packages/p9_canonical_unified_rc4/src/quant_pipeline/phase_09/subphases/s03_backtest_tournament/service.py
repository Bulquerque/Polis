"""High-level composition of P9.S3.M01-M07.

The service is intentionally thin: it composes explicit module services and
requires a typed metric-input provider instead of interpreting P8 payloads.
"""

from __future__ import annotations

from typing import Protocol

from .common import NonEmptyStr, StrictModel
from .comparison_models import ComparisonPolicy, ConfigurationLineage, TrialComparisonResult
from .execution_models import PhaseName, TrialExecutionLedger, TrialExecutionPlan
from .integrity_models import BacktestQualificationReceipt, P8EvaluationHandoff, QualificationState
from .m01_temporal_plan import build_temporal_evaluation_plan
from .m02_purged_walk_forward import build_purged_walk_forward_assignments
from .m03_backtest_runner import PhaseRunnerRegistry, execute_trial_plan
from .m04_integrity_replay import qualify_backtest
from .m05_competition_metric import compute_competition_score
from .m06_score_aggregation import aggregate_scores
from .m07_provisional_mcs import compare_trials
from .scoring_models import (
    CompetitionMetricPolicy,
    CompetitionScoreRecord,
    MetricInputRecord,
    ScoreAggregationPolicy,
    ScoreAggregationResult,
    ScoreContext,
)
from .temporal_models import (
    FoldAssignmentPanel,
    SampleRecord,
    SplitIntegrityReceipt,
    TemporalEvaluationPlan,
    TemporalPlanPolicy,
)


class MetricInputProvider(Protocol):
    def build(
        self,
        handoff: P8EvaluationHandoff,
        qualification: BacktestQualificationReceipt,
    ) -> tuple[MetricInputRecord, NonEmptyStr]: ...


class S3TournamentResult(StrictModel):
    temporal_plan: TemporalEvaluationPlan
    assignments: FoldAssignmentPanel
    split_receipt: SplitIntegrityReceipt
    execution_ledger: TrialExecutionLedger
    qualifications: tuple[BacktestQualificationReceipt, ...]
    scores: tuple[CompetitionScoreRecord, ...]
    aggregation: ScoreAggregationResult
    comparisons: tuple[TrialComparisonResult, ...]


class S3TournamentService:
    def __init__(self, runner_registry: PhaseRunnerRegistry) -> None:
        self.runner_registry = runner_registry

    def run(
        self,
        *,
        temporal_policy: TemporalPlanPolicy,
        samples: tuple[SampleRecord, ...],
        trial_plan: TrialExecutionPlan,
        metric_policy: CompetitionMetricPolicy,
        aggregation_policy: ScoreAggregationPolicy,
        comparison_policy: ComparisonPolicy,
        configuration_lineage: tuple[ConfigurationLineage, ...],
        metric_input_provider: MetricInputProvider,
    ) -> S3TournamentResult:
        temporal_plan = build_temporal_evaluation_plan(temporal_policy)
        assignments, split_receipt = build_purged_walk_forward_assignments(temporal_plan, samples)
        if split_receipt.status != "VALID":
            raise ValueError("temporal split did not qualify")

        execution_ledger = execute_trial_plan(trial_plan, self.runner_registry)
        qualifications: list[BacktestQualificationReceipt] = []
        contexts: list[ScoreContext] = []
        scores: list[CompetitionScoreRecord] = []
        for bundle in execution_ledger.bundles:
            p8_results = [result for result in bundle.phase_results if result.phase is PhaseName.P8]
            if not p8_results or p8_results[0].p8_handoff is None:
                continue
            handoff = p8_results[0].p8_handoff
            qualification = qualify_backtest(handoff)
            qualifications.append(qualification)
            accepted_states = {
                QualificationState.QUALIFIED,
                QualificationState.NO_ACTION_VALID,
            }
            if qualification.state not in accepted_states:
                continue
            metric_input, cohort_id = metric_input_provider.build(handoff, qualification)
            score = compute_competition_score(metric_policy, metric_input)
            scores.append(score)
            contexts.append(ScoreContext(score=score, cohort_id=cohort_id))

        aggregation = aggregate_scores(
            tuple(contexts),
            aggregation_policy,
            expected_fold_ids=tuple(fold.fold_id for fold in temporal_plan.folds),
        )
        cohorts = sorted({item.cohort_id for item in aggregation.aggregates})
        comparisons = tuple(
            compare_trials(
                aggregation.aggregates,
                aggregation.loss_series,
                configuration_lineage,
                comparison_policy,
                cohort_id=cohort,
            )
            for cohort in cohorts
        )
        return S3TournamentResult(
            temporal_plan=temporal_plan,
            assignments=assignments,
            split_receipt=split_receipt,
            execution_ledger=execution_ledger,
            qualifications=tuple(qualifications),
            scores=tuple(scores),
            aggregation=aggregation,
            comparisons=comparisons,
        )
