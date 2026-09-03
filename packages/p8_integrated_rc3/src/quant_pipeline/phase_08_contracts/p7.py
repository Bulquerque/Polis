"""P7 → P8 ranking handoff contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from .base import AwareDatetime, NonEmptyStr, SHA256Str, StrictModel
from .common import ArtifactReference
from .enums import ConfidenceState, P7TerminalState, ScoreSemantics


class RankedCandidateRecord(StrictModel):
    candidate_id: NonEmptyStr
    canonical_candidate_id: NonEmptyStr
    comparison_group_id: NonEmptyStr
    rank: int = Field(ge=1, strict=True)
    rank_tier: NonEmptyStr | None = None
    score_semantics: ScoreSemantics = ScoreSemantics.ORDINAL
    score_value: Decimal | None = None
    confidence_state: ConfidenceState = ConfidenceState.UNAVAILABLE
    confidence_calibration_ref: ArtifactReference | None = None
    p6_economic_package_ref: ArtifactReference
    decision_trace_ref: ArtifactReference
    thesis_card_ref: ArtifactReference | None = None
    score_decomposition_ref: ArtifactReference | None = None

    @model_validator(mode="after")
    def validate_score_semantics(self) -> Self:
        if self.score_semantics is ScoreSemantics.ORDINAL and self.score_value is not None:
            raise ValueError("ORDINAL score must not carry a cardinal score_value")
        if self.score_semantics is not ScoreSemantics.ORDINAL:
            if self.score_value is None:
                raise ValueError("cardinal score semantics require score_value")
            if self.confidence_state is not ConfidenceState.CALIBRATED:
                raise ValueError("cardinal score semantics require CALIBRATED confidence")
        if self.confidence_state is ConfidenceState.CALIBRATED and self.confidence_calibration_ref is None:
            raise ValueError("CALIBRATED confidence requires confidence_calibration_ref")
        return self


class P7TerminalCandidateRecord(StrictModel):
    candidate_id: NonEmptyStr
    terminal_state: P7TerminalState
    reason_codes: tuple[NonEmptyStr, ...] = Field(min_length=1)
    missing_evidence_refs: tuple[ArtifactReference, ...] = Field(default_factory=tuple)
    p6_economic_package_ref: ArtifactReference | None = None


class ComparisonGroupRecord(StrictModel):
    comparison_group_id: NonEmptyStr
    objective_family: NonEmptyStr
    underlying_scope: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    horizon_scope: NonEmptyStr
    capital_at_risk_bucket: NonEmptyStr | None = None
    liquidity_bucket: NonEmptyStr | None = None
    member_candidate_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    comparability_policy_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_unique_members(self) -> Self:
        if len(set(self.member_candidate_ids)) != len(self.member_candidate_ids):
            raise ValueError("comparison-group member_candidate_ids must be unique")
        return self


class P7RankingHandoffV1(StrictModel):
    handoff_id: NonEmptyStr
    contract_version: Literal["P7_TO_P8_RANKING_HANDOFF_V1"]
    schema_version: Literal["1.0.0"]
    producer_phase: Literal["P7"]
    producer_release: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    decision_time: AwareDatetime
    market_cutoff_at: AwareDatetime
    computed_at: AwareDatetime
    recorded_at: AwareDatetime
    available_at: AwareDatetime
    content_sha256: SHA256Str
    received_candidate_ids: tuple[NonEmptyStr, ...]
    ranked: tuple[RankedCandidateRecord, ...] = Field(default_factory=tuple)
    eligibility_blocked: tuple[P7TerminalCandidateRecord, ...] = Field(default_factory=tuple)
    safety_blocked: tuple[P7TerminalCandidateRecord, ...] = Field(default_factory=tuple)
    abstained: tuple[P7TerminalCandidateRecord, ...] = Field(default_factory=tuple)
    comparison_groups: tuple[ComparisonGroupRecord, ...] = Field(default_factory=tuple)
    artifact_refs: tuple[ArtifactReference, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_time_and_identity(self) -> Self:
        if self.market_cutoff_at > self.decision_time:
            raise ValueError("market_cutoff_at must not be after P7 decision_time")
        if self.decision_time > self.computed_at:
            raise ValueError("computed_at must not be before decision_time")
        if self.computed_at > self.recorded_at:
            raise ValueError("recorded_at must not be before computed_at")
        if self.recorded_at > self.available_at:
            raise ValueError("available_at must not be before recorded_at")
        if len(set(self.received_candidate_ids)) != len(self.received_candidate_ids):
            raise ValueError("received_candidate_ids must be unique")
        group_ids = [group.comparison_group_id for group in self.comparison_groups]
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("comparison_group_id must be unique")
        return self
