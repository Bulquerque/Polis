from __future__ import annotations

from .base import NonEmptyStr, StrictModel
from .cohort import CommitmentMatchReport, FrozenEvaluationCohort, HoldoutContaminationReport
from .lineage import LineageGapReport, LineageResolutionReceipt, ResolvedLineageGraph
from .maturity import EvaluationEligibilityPanel, MaturityDecisionTrace, OutcomeMaturityPanel
from .outcomes import (
    CounterfactualMarkPanel,
    MarkQualityReport,
    OutcomeAssemblyReceipt,
    RealizedOutcomePanel,
)
from .receipts import ModuleExecutionReceipt, SubphaseExecutionReceipt
from .replay import ReconstructedStateHashPanel, ReplayExceptionPanel, ReplayIntegrityReport
from .validation import HandoffValidationReport, ValidatedP8EvaluationHandoff


class S1ExecutionOutputs(StrictModel):
    validated_handoff: ValidatedP8EvaluationHandoff | None = None
    handoff_report: HandoffValidationReport
    lineage_graph: ResolvedLineageGraph | None = None
    lineage_gap_report: LineageGapReport | None = None
    lineage_receipt: LineageResolutionReceipt | None = None
    replay_report: ReplayIntegrityReport | None = None
    replay_hashes: ReconstructedStateHashPanel | None = None
    replay_exceptions: ReplayExceptionPanel | None = None
    maturity_panel: OutcomeMaturityPanel | None = None
    eligibility_panel: EvaluationEligibilityPanel | None = None
    maturity_trace: MaturityDecisionTrace | None = None
    realized_outcomes: RealizedOutcomePanel | None = None
    counterfactual_marks: CounterfactualMarkPanel | None = None
    mark_quality_report: MarkQualityReport | None = None
    outcome_assembly_receipt: OutcomeAssemblyReceipt | None = None
    frozen_cohort: FrozenEvaluationCohort | None = None
    commitment_report: CommitmentMatchReport | None = None
    holdout_report: HoldoutContaminationReport | None = None
    module_receipts: tuple[ModuleExecutionReceipt, ...]
    subphase_receipt: SubphaseExecutionReceipt
    limitations: tuple[NonEmptyStr, ...] = ()
