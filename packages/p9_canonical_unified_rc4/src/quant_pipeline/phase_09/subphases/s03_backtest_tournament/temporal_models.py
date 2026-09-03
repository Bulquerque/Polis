"""Typed contracts for temporal planning and purged walk-forward splitting."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .common import DurationSpec, NonEmptyStr, Sha256, StrictModel, TimeWindow, UtcDateTime


class WindowMode(StrEnum):
    EXPANDING = "EXPANDING"
    ROLLING = "ROLLING"


class SampleRole(StrEnum):
    TRAIN = "TRAIN"
    TUNING = "TUNING"
    TEST = "TEST"
    EXCLUDED = "EXCLUDED"


class TemporalPlanPolicy(StrictModel):
    policy_id: NonEmptyStr
    dataset_window: TimeWindow
    initial_train: DurationSpec
    tuning: DurationSpec
    test: DurationSpec
    step: DurationSpec
    embargo: DurationSpec
    holdout: DurationSpec
    window_mode: WindowMode = WindowMode.EXPANDING
    max_train: DurationSpec | None = None
    minimum_outer_folds: int = Field(default=2, ge=1)
    allow_overlapping_test_windows: bool = False

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        positive = {
            "initial_train": self.initial_train.seconds,
            "tuning": self.tuning.seconds,
            "test": self.test.seconds,
            "step": self.step.seconds,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.holdout.seconds <= 0:
            raise ValueError("holdout must be positive")
        if self.embargo.seconds < 0:
            raise ValueError("embargo must be non-negative")
        if not self.allow_overlapping_test_windows and self.step.seconds < self.test.seconds:
            raise ValueError(
                "step must be >= test duration unless overlapping tests are explicitly allowed"
            )
        if self.window_mode is WindowMode.ROLLING:
            if self.max_train is None or self.max_train.seconds < self.initial_train.seconds:
                raise ValueError("rolling mode requires max_train >= initial_train")
        if self.window_mode is WindowMode.EXPANDING and self.max_train is not None:
            raise ValueError("max_train is only valid in rolling mode")
        return self


class FoldDefinition(StrictModel):
    fold_id: NonEmptyStr
    outer_index: int = Field(ge=0)
    train_window: TimeWindow
    tuning_window: TimeWindow
    test_window: TimeWindow
    embargo: DurationSpec

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not (
            self.train_window.end <= self.tuning_window.start
            and self.tuning_window.end <= self.test_window.start
        ):
            raise ValueError("train, tuning, and test windows must be ordered and non-overlapping")
        if self.train_window.end + self.embargo.as_timedelta() > self.tuning_window.start:
            raise ValueError("train/tuning embargo is violated")
        if self.tuning_window.end + self.embargo.as_timedelta() > self.test_window.start:
            raise ValueError("tuning/test embargo is violated")
        return self


class HoldoutFirewallPolicy(StrictModel):
    holdout_window: TimeWindow
    access_policy_id: NonEmptyStr
    allowed_consumer_module_ids: tuple[NonEmptyStr, ...] = ()
    opened_at: UtcDateTime | None = None


class TemporalEvaluationPlan(StrictModel):
    plan_id: NonEmptyStr
    policy_id: NonEmptyStr
    policy_sha256: Sha256
    folds: tuple[FoldDefinition, ...]
    holdout_firewall: HoldoutFirewallPolicy
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_folds(self) -> Self:
        if not self.folds:
            raise ValueError("at least one fold is required")
        ids = [fold.fold_id for fold in self.folds]
        if len(ids) != len(set(ids)):
            raise ValueError("fold IDs must be unique")
        previous_start = None
        for fold in self.folds:
            if previous_start is not None and fold.test_window.start <= previous_start:
                raise ValueError("test windows must advance strictly in time")
            if fold.test_window.end > self.holdout_firewall.holdout_window.start:
                raise ValueError("fold overlaps reserved holdout")
            previous_start = fold.test_window.start
        return self


class SampleRecord(StrictModel):
    record_id: NonEmptyStr
    entity_id: NonEmptyStr
    decision_time: UtcDateTime
    available_at: UtcDateTime
    label_start_time: UtcDateTime
    label_end_time: UtcDateTime
    vintage_time: UtcDateTime

    @model_validator(mode="after")
    def validate_times(self) -> Self:
        if self.label_end_time <= self.label_start_time:
            raise ValueError("label interval must have positive duration")
        if self.label_start_time < self.decision_time:
            raise ValueError("label_start_time cannot precede decision_time")
        return self


class FoldAssignment(StrictModel):
    fold_id: NonEmptyStr
    record_id: NonEmptyStr
    entity_id: NonEmptyStr
    role: SampleRole
    reason_codes: tuple[NonEmptyStr, ...] = ()


class FoldAssignmentPanel(StrictModel):
    plan_id: NonEmptyStr
    assignments: tuple[FoldAssignment, ...]
    content_sha256: Sha256


class SplitCount(StrictModel):
    fold_id: NonEmptyStr
    train_count: int = Field(ge=0)
    tuning_count: int = Field(ge=0)
    test_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    purged_count: int = Field(ge=0)
    pit_rejected_count: int = Field(ge=0)


class SplitIntegrityReceipt(StrictModel):
    plan_id: NonEmptyStr
    status: NonEmptyStr
    counts: tuple[SplitCount, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()
    content_sha256: Sha256
