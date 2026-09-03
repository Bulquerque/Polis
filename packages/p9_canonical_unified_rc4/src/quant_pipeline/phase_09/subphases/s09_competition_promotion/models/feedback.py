from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..enums import (
    EvidenceQuality,
    FeedbackBuildState,
    FeedbackEffectType,
    FeedbackPhase,
    FeedbackValidationState,
)
from .common import (
    CycleRef,
    EvidenceReference,
    LongText,
    NonEmptyStr,
    PolicyId,
    ReasonCode,
    StrictModel,
)


class NumericChangeBounds(StrictModel):
    parameter_name: NonEmptyStr
    minimum: float | None = None
    maximum: float | None = None
    maximum_absolute_delta: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "NumericChangeBounds":
        if self.minimum is None and self.maximum is None and self.maximum_absolute_delta is None:
            raise ValueError("at least one numeric bound is required")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class CategoricalChangeBounds(StrictModel):
    parameter_name: NonEmptyStr
    allowed_values: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_values(self) -> "CategoricalChangeBounds":
        if not self.allowed_values:
            raise ValueError("allowed values cannot be empty")
        if len(set(self.allowed_values)) != len(self.allowed_values):
            raise ValueError("allowed values must be unique")
        return self


class FeedbackPolicyTarget(StrictModel):
    target_phase: FeedbackPhase
    target_policy_id: PolicyId
    target_policy_version: NonEmptyStr
    allowed_feedback_types: tuple[NonEmptyStr, ...]
    numeric_bounds: tuple[NumericChangeBounds, ...] = ()
    categorical_bounds: tuple[CategoricalChangeBounds, ...] = ()
    requires_p0_authorization_for: tuple[FeedbackEffectType, ...] = ()


class FeedbackPolicyRegistry(StrictModel):
    registry_version: NonEmptyStr
    targets: tuple[FeedbackPolicyTarget, ...]

    @model_validator(mode="after")
    def validate_unique_targets(self) -> "FeedbackPolicyRegistry":
        keys = [(target.target_phase, target.target_policy_id) for target in self.targets]
        if len(set(keys)) != len(keys):
            raise ValueError("feedback targets must be unique by phase and policy ID")
        return self

    def resolve(self, phase: FeedbackPhase, policy_id: str) -> FeedbackPolicyTarget | None:
        return next(
            (
                target
                for target in self.targets
                if target.target_phase == phase and target.target_policy_id == policy_id
            ),
            None,
        )


class RootCauseEvidence(StrictModel):
    root_cause_id: NonEmptyStr
    target_phase: FeedbackPhase
    target_policy_id: PolicyId
    feedback_type: NonEmptyStr
    effect_type: FeedbackEffectType
    summary: LongText
    evidence_refs: tuple[EvidenceReference, ...]
    evidence_quality: EvidenceQuality
    confidence: float = Field(ge=0.0, le=1.0)
    economic_materiality: float = Field(ge=0.0)
    numeric_change_bounds: tuple[NumericChangeBounds, ...] = ()
    categorical_change_bounds: tuple[CategoricalChangeBounds, ...] = ()
    atomic_group_id: NonEmptyStr | None = None


class FeedbackEffectivenessRecord(StrictModel):
    target_phase: FeedbackPhase
    target_policy_id: PolicyId
    effectiveness_score: float = Field(ge=-1.0, le=1.0)
    regressive: bool


class FeedbackPackageBase(StrictModel):
    feedback_id: NonEmptyStr
    source_cycle: CycleRef
    target_cycle: CycleRef
    target_phase: FeedbackPhase
    target_policy_id: PolicyId
    target_policy_version: NonEmptyStr
    feedback_type: NonEmptyStr
    effect_type: FeedbackEffectType
    evidence_refs: tuple[EvidenceReference, ...]
    confidence: float = Field(ge=0.0, le=1.0)
    economic_materiality: float = Field(ge=0.0)
    numeric_change_bounds: tuple[NumericChangeBounds, ...] = ()
    categorical_change_bounds: tuple[CategoricalChangeBounds, ...] = ()
    promotion_dependency: NonEmptyStr | None = None
    expires_after_cycle: CycleRef
    supersedes_feedback_id: NonEmptyStr | None = None
    atomic_group_id: NonEmptyStr | None = None
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_cycle_and_bounds(self) -> "FeedbackPackageBase":
        if self.target_cycle.ordinal <= self.source_cycle.ordinal:
            raise ValueError("feedback target cycle must be strictly after source cycle")
        if self.expires_after_cycle.ordinal < self.target_cycle.ordinal:
            raise ValueError("feedback cannot expire before its target cycle")
        if not self.evidence_refs:
            raise ValueError("feedback requires evidence references")
        if not self.numeric_change_bounds and not self.categorical_change_bounds:
            if self.effect_type != FeedbackEffectType.RESEARCH_REQUEST:
                raise ValueError("non-research feedback requires explicit change bounds")
        return self


class P9P5ForecastFeedback(FeedbackPackageBase):
    target_phase: Literal[FeedbackPhase.P5] = FeedbackPhase.P5


class P9P6SynthesisFeedback(FeedbackPackageBase):
    target_phase: Literal[FeedbackPhase.P6] = FeedbackPhase.P6


class P9P7RankingFeedback(FeedbackPackageBase):
    target_phase: Literal[FeedbackPhase.P7] = FeedbackPhase.P7


class P9P8PortfolioExecutionFeedback(FeedbackPackageBase):
    target_phase: Literal[FeedbackPhase.P8] = FeedbackPhase.P8


FeedbackPackage = (
    P9P5ForecastFeedback
    | P9P6SynthesisFeedback
    | P9P7RankingFeedback
    | P9P8PortfolioExecutionFeedback
)


class FeedbackCandidateManifest(StrictModel):
    build_state: FeedbackBuildState
    feedback_packages: tuple[FeedbackPackage, ...]
    rejected_root_cause_ids: tuple[NonEmptyStr, ...] = ()
    warnings: tuple[LongText, ...] = ()

    @model_validator(mode="after")
    def validate_manifest(self) -> "FeedbackCandidateManifest":
        ids = [package.feedback_id for package in self.feedback_packages]
        if len(set(ids)) != len(ids):
            raise ValueError("feedback IDs must be unique")
        was_built = self.build_state == FeedbackBuildState.FEEDBACK_CANDIDATE_BUILT
        if was_built and not self.feedback_packages:
            raise ValueError("built feedback state requires at least one package")
        return self


class TargetCapabilitySnapshot(StrictModel):
    target_phase: FeedbackPhase
    target_policy_id: PolicyId
    target_policy_version: NonEmptyStr
    available: bool
    accepted_contract_major: int = Field(ge=1)


class FeedbackActivationLedgerEntry(StrictModel):
    feedback_id: NonEmptyStr
    state: FeedbackValidationState
    target_cycle: CycleRef


class FeedbackValidationDecision(StrictModel):
    feedback_id: NonEmptyStr
    state: FeedbackValidationState
    reason_codes: tuple[ReasonCode, ...] = ()
    requires_p0_authorization: bool


class ValidatedNextCycleFeedbackManifest(StrictModel):
    accepted: tuple[FeedbackPackage, ...]
    rejected: tuple[FeedbackPackage, ...]
    reserved: tuple[FeedbackPackage, ...]
    decisions: tuple[FeedbackValidationDecision, ...]

    @model_validator(mode="after")
    def validate_partition(self) -> "ValidatedNextCycleFeedbackManifest":
        accepted_ids = {package.feedback_id for package in self.accepted}
        rejected_ids = {package.feedback_id for package in self.rejected}
        reserved_ids = {package.feedback_id for package in self.reserved}
        has_overlap = bool(
            accepted_ids & rejected_ids
            or accepted_ids & reserved_ids
            or rejected_ids & reserved_ids
        )
        if has_overlap:
            raise ValueError("accepted, rejected, and reserved feedback sets must be disjoint")
        decision_ids = {decision.feedback_id for decision in self.decisions}
        if decision_ids != accepted_ids | rejected_ids | reserved_ids:
            raise ValueError("feedback decisions must cover the full feedback partition")
        return self


class FeedbackBuildPolicy(StrictModel):
    minimum_confidence: float = Field(ge=0.0, le=1.0, default=0.75)
    minimum_economic_materiality: float = Field(ge=0.0, default=0.0)
    expiry_after_cycles: int = Field(ge=1, default=3)


class FeedbackActivationGateOutput(StrictModel):
    manifest: ValidatedNextCycleFeedbackManifest
    pending_p0_count: int = Field(ge=0)
    future_validated_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    reserved_count: int = Field(ge=0)
