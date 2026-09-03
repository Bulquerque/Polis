from __future__ import annotations

from dataclasses import dataclass

from quant_pipeline.phase_09.contracts.base import EvidenceClass
from quant_pipeline.phase_09.contracts.cohort import (
    CohortPolicyRegistry,
    CommitmentMatchReport,
    CommitmentMatchState,
    FrozenCohortRecord,
    FrozenEvaluationCohort,
    HoldoutAccessLedger,
    HoldoutContaminationReport,
    HoldoutPurpose,
    ResearchCommitment,
    ResearchCommitmentRegistry,
)
from quant_pipeline.phase_09.contracts.integrity import payload_sha256
from quant_pipeline.phase_09.contracts.lineage import (
    LineageResolutionStatus,
    ResolvedLineageGraph,
)
from quant_pipeline.phase_09.contracts.maturity import (
    MaturityState,
    MaturitySubjectManifest,
    OutcomeMaturityPanel,
)
from quant_pipeline.phase_09.contracts.outcomes import RealizedOutcomePanel


@dataclass(frozen=True, slots=True)
class CohortMatchOutcome:
    cohort: FrozenEvaluationCohort | None
    report: CommitmentMatchReport
    holdout_report: HoldoutContaminationReport


class EvaluationCohortAndCommitmentMatcher:
    module_id = "P9.S1.M06"

    def match(
        self,
        *,
        subjects: MaturitySubjectManifest,
        maturity_panel: OutcomeMaturityPanel,
        outcomes: RealizedOutcomePanel,
        lineage: ResolvedLineageGraph,
        commitments: ResearchCommitmentRegistry,
        cohort_policies: CohortPolicyRegistry,
        holdout_access: HoldoutAccessLedger,
        evaluation_as_of,
        metric_family: str = "primary",
    ) -> CohortMatchOutcome:
        commitment = self._active_commitment(commitments, evaluation_as_of)
        if commitment is None:
            report = CommitmentMatchReport(
                state=CommitmentMatchState.COMMITMENT_MISMATCH,
                commitment_id=None,
                policy_id=None,
                eligible_count=0,
                excluded_count=len(outcomes.records),
                reason_codes=("P9_S1_COMMITMENT_MISSING",),
            )
            return CohortMatchOutcome(
                cohort=None,
                report=report,
                holdout_report=HoldoutContaminationReport(contaminated=False),
            )
        policy = cohort_policies.policy(commitment.cohort_policy_id)
        if policy is None:
            report = CommitmentMatchReport(
                state=CommitmentMatchState.COMMITMENT_MISMATCH,
                commitment_id=commitment.commitment_id,
                policy_id=commitment.cohort_policy_id,
                eligible_count=0,
                excluded_count=len(outcomes.records),
                reason_codes=("P9_S1_COHORT_POLICY_MISSING",),
            )
            return CohortMatchOutcome(
                cohort=None,
                report=report,
                holdout_report=HoldoutContaminationReport(contaminated=False),
            )

        contamination_ids = tuple(
            sorted(
                record.access_id
                for record in holdout_access.records
                if record.dataset_id in commitment.holdout_dataset_ids
                and record.accessed_at <= evaluation_as_of
                and (
                    not record.approved
                    or record.purpose in {HoldoutPurpose.TUNING, HoldoutPurpose.DIAGNOSTIC}
                )
            )
        )
        holdout_report = HoldoutContaminationReport(
            contaminated=bool(contamination_ids),
            access_ids=contamination_ids,
            reason_codes=("P9_S1_HOLDOUT_ACCESSED_EARLY",) if contamination_ids else (),
        )

        subjects_by_id = {subject.subject_id: subject for subject in subjects.payload.subjects}
        maturity_by_id = {
            decision.subject_id: decision
            for decision in maturity_panel.decisions
            if decision.metric_family == metric_family
        }
        complete_lineage = lineage.status in {
            LineageResolutionStatus.RESOLVED_COMPLETE,
            LineageResolutionStatus.RESOLVED_WITH_NONMATERIAL_GAPS,
        }
        included: list[FrozenCohortRecord] = []
        excluded: list[str] = []
        for outcome in outcomes.records:
            subject = subjects_by_id.get(outcome.subject_id)
            maturity = maturity_by_id.get(outcome.subject_id)
            if subject is None or maturity is None:
                excluded.append(outcome.subject_id)
                continue
            if subject.target_type not in policy.allowed_target_types:
                excluded.append(outcome.subject_id)
                continue
            if outcome.evidence_class not in policy.allowed_evidence_classes:
                excluded.append(outcome.subject_id)
                continue
            if maturity.state not in {
                MaturityState.MATURED,
                MaturityState.SETTLED,
                MaturityState.PARTIALLY_MATURED,
            }:
                excluded.append(outcome.subject_id)
                continue
            if not maturity.eligible:
                excluded.append(outcome.subject_id)
                continue
            if policy.require_complete_lineage and not complete_lineage:
                excluded.append(outcome.subject_id)
                continue
            included.append(
                FrozenCohortRecord(
                    subject_id=outcome.subject_id,
                    target_type=subject.target_type,
                    evidence_class=outcome.evidence_class,
                    outcome_record_sha256=payload_sha256(outcome),
                    lineage_complete=complete_lineage,
                )
            )

        if holdout_report.contaminated:
            state = CommitmentMatchState.HOLDOUT_CONTAMINATED
            reason_codes = ("P9_S1_HOLDOUT_ACCESSED_EARLY",)
        elif len(included) < policy.minimum_sample:
            state = CommitmentMatchState.INSUFFICIENT_ELIGIBLE_SAMPLE
            reason_codes = ("P9_S1_COHORT_INSUFFICIENT_SAMPLE",)
        elif excluded:
            state = CommitmentMatchState.COHORT_LIMITED
            reason_codes = ()
        else:
            state = CommitmentMatchState.COHORT_FROZEN
            reason_codes = ()

        cohort: FrozenEvaluationCohort | None = None
        if state in {
            CommitmentMatchState.COHORT_FROZEN,
            CommitmentMatchState.COHORT_LIMITED,
        }:
            cohort_payload = {
                "commitment_id": commitment.commitment_id,
                "policy_id": policy.policy_id,
                "frozen_at": evaluation_as_of,
                "records": tuple(sorted(included, key=lambda item: item.subject_id)),
                "excluded_subject_ids": tuple(sorted(excluded)),
            }
            cohort_hash = payload_sha256(cohort_payload)
            cohort = FrozenEvaluationCohort(
                cohort_id=f"cohort-{cohort_hash[:16]}",
                commitment_id=commitment.commitment_id,
                policy_id=policy.policy_id,
                frozen_at=evaluation_as_of,
                records=cohort_payload["records"],
                excluded_subject_ids=cohort_payload["excluded_subject_ids"],
                cohort_sha256=cohort_hash,
            )
        report = CommitmentMatchReport(
            state=state,
            commitment_id=commitment.commitment_id,
            policy_id=policy.policy_id,
            eligible_count=len(included),
            excluded_count=len(excluded),
            reason_codes=reason_codes,
            limitations=(
                ("lineage is not fully complete",)
                if not complete_lineage
                else ()
            ),
        )
        return CohortMatchOutcome(cohort=cohort, report=report, holdout_report=holdout_report)

    @staticmethod
    def _active_commitment(
        registry: ResearchCommitmentRegistry,
        evaluation_as_of,
    ) -> ResearchCommitment | None:
        candidates = [
            commitment
            for commitment in registry.commitments
            if commitment.created_at <= evaluation_as_of
            and commitment.effective_from <= evaluation_as_of
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (item.effective_from, item.created_at, item.commitment_id),
        )
