from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    FeedbackPackage,
    ValidatedNextCycleFeedbackManifest,
)

from ..enums import FeedbackLifecycleState, MetricDirection, OutcomeMaturity
from ..hashing import sha256_hex
from .common import (
    CycleRef,
    EvidenceReference,
    FeedbackId,
    LongText,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcTimestampedModel,
)


class FeedbackAuthorizationRecord(UtcTimestampedModel):
    feedback_id: FeedbackId
    authorization_id: NonEmptyStr
    authorized: bool
    authorized_at: datetime
    evidence_refs: tuple[EvidenceReference, ...] = ()


class PolicyChange(StrictModel):
    parameter_name: NonEmptyStr
    before_value: NonEmptyStr
    after_value: NonEmptyStr


class FeedbackActivationRecord(UtcTimestampedModel):
    feedback_id: FeedbackId
    activated: bool
    target_cycle: CycleRef
    activated_at: datetime | None = None
    target_phase: NonEmptyStr
    target_policy_id: NonEmptyStr
    target_metric_id: NonEmptyStr
    target_policy_version_before: NonEmptyStr
    target_policy_version_after: NonEmptyStr
    policy_before_sha256: Sha256Hex
    policy_after_sha256: Sha256Hex
    exact_policy_diff: tuple[PolicyChange, ...]
    simultaneous_feedback_ids: tuple[FeedbackId, ...] = ()
    reverted: bool = False

    @model_validator(mode="after")
    def validate_activation(self) -> "FeedbackActivationRecord":
        if self.activated and self.activated_at is None:
            raise ValueError("activated feedback requires activated_at")
        if self.activated and not self.exact_policy_diff:
            raise ValueError("activated feedback requires exact policy diff")
        if self.policy_before_sha256 == self.policy_after_sha256 and self.activated:
            raise ValueError("activated feedback must change the policy hash")
        if self.feedback_id in self.simultaneous_feedback_ids:
            raise ValueError("feedback cannot list itself as a simultaneous intervention")
        return self


class FeedbackOutcomePair(StrictModel):
    feedback_id: FeedbackId
    pair_id: NonEmptyStr
    metric_id: NonEmptyStr
    cohort_id: NonEmptyStr
    baseline_value: float
    intervention_value: float
    maturity: OutcomeMaturity
    comparable: bool = True
    evidence_refs: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_values(self) -> "FeedbackOutcomePair":
        for value in (self.baseline_value, self.intervention_value):
            if not (-float("inf") < value < float("inf")):
                raise ValueError("feedback outcome values must be finite")
        return self


class GuardrailObservation(StrictModel):
    feedback_id: FeedbackId
    guardrail_id: NonEmptyStr
    direction: MetricDirection
    baseline_value: float
    intervention_value: float
    maximum_allowed_regression: float = Field(ge=0.0)
    critical: bool = False
    evidence_refs: tuple[EvidenceReference, ...] = ()


class MetricEvaluationPolicy(StrictModel):
    metric_id: NonEmptyStr
    direction: MetricDirection
    minimum_material_effect: float = Field(ge=0.0)
    minimum_observations: int = Field(default=5, ge=2)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)


class FeedbackEvaluationPolicy(StrictModel):
    policy_id: NonEmptyStr
    metrics: tuple[MetricEvaluationPolicy, ...]
    reject_unisolated_interventions: bool = True

    @model_validator(mode="after")
    def validate_unique_metrics(self) -> "FeedbackEvaluationPolicy":
        ids = [metric.metric_id for metric in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("feedback evaluation metric IDs must be unique")
        return self

    def resolve(self, metric_id: str) -> MetricEvaluationPolicy | None:
        return next((metric for metric in self.metrics if metric.metric_id == metric_id), None)


class FeedbackLifecycleEvent(UtcTimestampedModel):
    event_id: NonEmptyStr
    feedback_id: FeedbackId
    state: FeedbackLifecycleState
    cycle: CycleRef
    event_time: datetime
    reason_codes: tuple[ReasonCode, ...] = ()
    evidence_refs: tuple[EvidenceReference, ...] = ()


class FeedbackLifecycleLedger(StrictModel):
    previous_ledger_sha256: Sha256Hex | None = None
    events: tuple[FeedbackLifecycleEvent, ...]
    ledger_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_ledger(self) -> "FeedbackLifecycleLedger":
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("feedback lifecycle event IDs must be unique")
        grouped: dict[str, list[FeedbackLifecycleEvent]] = {}
        for event in self.events:
            grouped.setdefault(event.feedback_id, []).append(event)
        for events in grouped.values():
            ordered = sorted(events, key=lambda item: (item.cycle.ordinal, item.event_time))
            if tuple(events) != tuple(ordered):
                raise ValueError("feedback lifecycle events must be chronologically ordered")
        payload = {
            "previous_ledger_sha256": self.previous_ledger_sha256,
            "events": self.events,
        }
        if self.ledger_sha256 != sha256_hex(payload):
            raise ValueError("feedback lifecycle ledger hash mismatch")
        return self


class FeedbackEffectivenessAssessment(StrictModel):
    feedback_id: FeedbackId
    state: FeedbackLifecycleState
    metric_id: NonEmptyStr | None = None
    sample_size: int = Field(ge=0)
    mean_effect: float | None = None
    standard_error: float | None = Field(default=None, ge=0.0)
    confidence_lower: float | None = None
    confidence_upper: float | None = None
    guardrail_regressions: tuple[NonEmptyStr, ...] = ()
    policy_diff_sha256: Sha256Hex | None = None
    confounded: bool = False
    evidence_refs: tuple[EvidenceReference, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_assessment(self) -> "FeedbackEffectivenessAssessment":
        interval = (self.confidence_lower, self.confidence_upper)
        if (interval[0] is None) != (interval[1] is None):
            raise ValueError("confidence interval bounds must be both present or both absent")
        if interval[0] is not None and interval[0] > interval[1]:
            raise ValueError("confidence interval lower bound cannot exceed upper bound")
        measured_states = {
            FeedbackLifecycleState.EFFECTIVE,
            FeedbackLifecycleState.INEFFECTIVE,
            FeedbackLifecycleState.REGRESSIVE,
            FeedbackLifecycleState.INCONCLUSIVE,
        }
        if self.state in measured_states and self.metric_id is None:
            raise ValueError("measured feedback states require a metric ID")
        return self


class FeedbackRegressionRecord(StrictModel):
    feedback_id: FeedbackId
    guardrail_id: NonEmptyStr
    adverse_change: float = Field(ge=0.0)
    critical: bool
    evidence_refs: tuple[EvidenceReference, ...] = ()


class FeedbackRegressionPanel(StrictModel):
    records: tuple[FeedbackRegressionRecord, ...]


class FeedbackEffectivenessReport(StrictModel):
    policy_id: NonEmptyStr
    assessments: tuple[FeedbackEffectivenessAssessment, ...]
    effective_count: int = Field(ge=0)
    ineffective_count: int = Field(ge=0)
    regressive_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    other_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "FeedbackEffectivenessReport":
        counts = {
            FeedbackLifecycleState.EFFECTIVE: self.effective_count,
            FeedbackLifecycleState.INEFFECTIVE: self.ineffective_count,
            FeedbackLifecycleState.REGRESSIVE: self.regressive_count,
            FeedbackLifecycleState.INCONCLUSIVE: self.inconclusive_count,
        }
        for state, expected in counts.items():
            actual = sum(assessment.state == state for assessment in self.assessments)
            if actual != expected:
                raise ValueError(f"feedback count mismatch for {state.value}")
        pending_states = {
            FeedbackLifecycleState.OUTCOME_NOT_MATURED,
            FeedbackLifecycleState.NOT_ACTIVATED,
        }
        actual_pending = sum(a.state in pending_states for a in self.assessments)
        if actual_pending != self.pending_count:
            raise ValueError("feedback pending count mismatch")
        classified = set(counts) | pending_states
        actual_other = sum(a.state not in classified for a in self.assessments)
        if actual_other != self.other_count:
            raise ValueError("feedback other-state count mismatch")
        return self


class FeedbackEffectivenessInputBundle(StrictModel):
    validated_feedback_manifest: ValidatedNextCycleFeedbackManifest
    feedback_packages: tuple[FeedbackPackage, ...]
    authorizations: tuple[FeedbackAuthorizationRecord, ...]
    activations: tuple[FeedbackActivationRecord, ...]
    outcome_pairs: tuple[FeedbackOutcomePair, ...]
    guardrail_observations: tuple[GuardrailObservation, ...] = ()
    evaluation_policy: FeedbackEvaluationPolicy
    previous_lifecycle_ledger: FeedbackLifecycleLedger | None = None
    evaluation_cycle: CycleRef

    @model_validator(mode="after")
    def validate_feedback_identity(self) -> "FeedbackEffectivenessInputBundle":
        package_ids = [package.feedback_id for package in self.feedback_packages]
        if len(package_ids) != len(set(package_ids)):
            raise ValueError("feedback packages must have unique IDs")
        manifest_ids = {
            package.feedback_id
            for package in (
                self.validated_feedback_manifest.accepted
                + self.validated_feedback_manifest.rejected
                + self.validated_feedback_manifest.reserved
            )
        }
        if set(package_ids) != manifest_ids:
            raise ValueError("feedback packages must match the validated manifest partition")
        return self


class FeedbackEffectivenessModuleOutput(StrictModel):
    report: FeedbackEffectivenessReport
    lifecycle_ledger: FeedbackLifecycleLedger
    regression_panel: FeedbackRegressionPanel
