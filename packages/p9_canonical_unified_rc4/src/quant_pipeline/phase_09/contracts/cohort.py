from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .base import EvidenceClass, NonEmptyStr, ReasonCode, Sha256Hex, StrictModel, UtcDateTime


class HoldoutPurpose(StrEnum):
    FINAL_EVALUATION = "FINAL_EVALUATION"
    TUNING = "TUNING"
    DIAGNOSTIC = "DIAGNOSTIC"
    OPERATIONS = "OPERATIONS"


class ResearchCommitment(StrictModel):
    commitment_id: NonEmptyStr
    created_at: UtcDateTime
    effective_from: UtcDateTime
    metric_ids: tuple[NonEmptyStr, ...]
    cohort_policy_id: NonEmptyStr
    holdout_dataset_ids: tuple[NonEmptyStr, ...] = ()
    champion_configuration_id: NonEmptyStr | None = None
    challenger_configuration_ids: tuple[NonEmptyStr, ...] = ()
    commitment_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_commitment(self) -> "ResearchCommitment":
        if self.effective_from < self.created_at:
            raise ValueError("effective_from must be >= created_at")
        if not self.metric_ids:
            raise ValueError("commitment requires at least one metric")
        if len(set(self.metric_ids)) != len(self.metric_ids):
            raise ValueError("metric_ids must be unique")
        return self


class ResearchCommitmentRegistry(StrictModel):
    commitments: tuple[ResearchCommitment, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "ResearchCommitmentRegistry":
        ids = [commitment.commitment_id for commitment in self.commitments]
        if len(ids) != len(set(ids)):
            raise ValueError("commitment IDs must be unique")
        return self


class HoldoutAccessRecord(StrictModel):
    access_id: NonEmptyStr
    dataset_id: NonEmptyStr
    actor_id: NonEmptyStr
    accessed_at: UtcDateTime
    purpose: HoldoutPurpose
    approved: bool


class HoldoutAccessLedger(StrictModel):
    records: tuple[HoldoutAccessRecord, ...] = ()


class CohortPolicy(StrictModel):
    policy_id: NonEmptyStr
    allowed_target_types: tuple[NonEmptyStr, ...]
    allowed_evidence_classes: tuple[EvidenceClass, ...]
    minimum_sample: int = Field(ge=1)
    require_complete_lineage: bool = True
    include_abstentions: bool = True


class CohortPolicyRegistry(StrictModel):
    policies: tuple[CohortPolicy, ...]

    def policy(self, policy_id: str) -> CohortPolicy | None:
        return next((policy for policy in self.policies if policy.policy_id == policy_id), None)


class FrozenCohortRecord(StrictModel):
    subject_id: NonEmptyStr
    target_type: NonEmptyStr
    evidence_class: EvidenceClass
    outcome_record_sha256: Sha256Hex
    lineage_complete: bool


class FrozenEvaluationCohort(StrictModel):
    cohort_id: NonEmptyStr
    commitment_id: NonEmptyStr
    policy_id: NonEmptyStr
    frozen_at: UtcDateTime
    records: tuple[FrozenCohortRecord, ...]
    excluded_subject_ids: tuple[NonEmptyStr, ...]
    cohort_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_unique(self) -> "FrozenEvaluationCohort":
        record_ids = [record.subject_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("frozen cohort subject IDs must be unique")
        if set(record_ids) & set(self.excluded_subject_ids):
            raise ValueError("included and excluded subject IDs must be disjoint")
        return self


class CommitmentMatchState(StrEnum):
    COHORT_FROZEN = "COHORT_FROZEN"
    COHORT_LIMITED = "COHORT_LIMITED"
    COMMITMENT_MISMATCH = "COMMITMENT_MISMATCH"
    HOLDOUT_CONTAMINATED = "HOLDOUT_CONTAMINATED"
    INSUFFICIENT_ELIGIBLE_SAMPLE = "INSUFFICIENT_ELIGIBLE_SAMPLE"


class CommitmentMatchReport(StrictModel):
    state: CommitmentMatchState
    commitment_id: NonEmptyStr | None
    policy_id: NonEmptyStr | None
    eligible_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()


class HoldoutContaminationReport(StrictModel):
    contaminated: bool
    access_ids: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_contamination(self) -> "HoldoutContaminationReport":
        if self.contaminated and not self.access_ids:
            raise ValueError("contaminated report requires access IDs")
        if self.contaminated and not self.reason_codes:
            raise ValueError("contaminated report requires reason codes")
        return self
