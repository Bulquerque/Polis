from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from ..enums import ChangeOrigin, ContaminationState, LeaderboardState
from .common import ConfigId, LongText, NonEmptyStr, StrictModel, UtcTimestampedModel


class SubmissionChange(StrictModel):
    parameter_name: NonEmptyStr
    normalized_magnitude: float = Field(ge=0.0, le=1.0)
    origin: ChangeOrigin
    rationale: LongText


class SubmissionRecord(UtcTimestampedModel):
    submission_id: NonEmptyStr
    configuration_id: ConfigId
    submitted_at: datetime
    hypothesis_committed_at: datetime | None
    hypothesis_text_hash: NonEmptyStr | None
    public_score: float | None
    parent_submission_id: NonEmptyStr | None = None
    changes_after_parent: tuple[SubmissionChange, ...] = ()

    @model_validator(mode="after")
    def validate_submission(self) -> "SubmissionRecord":
        if (self.hypothesis_committed_at is None) != (self.hypothesis_text_hash is None):
            raise ValueError("hypothesis timestamp and hash must be present together")
        commitment_is_late = (
            self.hypothesis_committed_at is not None
            and self.hypothesis_committed_at >= self.submitted_at
        )
        if commitment_is_late:
            raise ValueError("hypothesis must be committed before submission")
        if self.parent_submission_id is None and self.changes_after_parent:
            raise ValueError("changes_after_parent require a parent submission")
        if self.public_score is not None and not (-float("inf") < self.public_score < float("inf")):
            raise ValueError("public score must be finite")
        return self


class LeaderboardPolicy(StrictModel):
    policy_id: NonEmptyStr
    maximum_submissions: int = Field(ge=1)
    information_budget: float = Field(gt=0.0)
    base_submission_cost: float = Field(gt=0.0)
    uncommitted_penalty: float = Field(ge=0.0)
    public_reaction_penalty: float = Field(ge=0.0)
    change_magnitude_weight: float = Field(ge=0.0)
    contamination_threshold: float = Field(gt=0.0)
    limited_use_threshold: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "LeaderboardPolicy":
        if self.limited_use_threshold >= self.contamination_threshold:
            raise ValueError("limited-use threshold must be below contamination threshold")
        if self.contamination_threshold > self.information_budget:
            raise ValueError("contamination threshold cannot exceed the information budget")
        return self


class SubmissionAssessment(StrictModel):
    submission_id: NonEmptyStr
    information_cost: float = Field(ge=0.0)
    cumulative_information_cost: float = Field(ge=0.0)
    contamination_state: ContaminationState
    reasons: tuple[NonEmptyStr, ...] = ()


class LeaderboardInformationBudgetReport(StrictModel):
    state: LeaderboardState
    policy_id: NonEmptyStr
    submission_count: int = Field(ge=0)
    total_information_cost: float = Field(ge=0.0)
    remaining_information_budget: float = Field(ge=0.0)
    assessments: tuple[SubmissionAssessment, ...]
    full_promotion_eligible: bool


class SubmissionEligibilityReceipt(StrictModel):
    configuration_id: ConfigId
    eligible_for_submission: bool
    eligible_for_full_promotion: bool
    leaderboard_state: LeaderboardState
    reasons: tuple[NonEmptyStr, ...] = ()
