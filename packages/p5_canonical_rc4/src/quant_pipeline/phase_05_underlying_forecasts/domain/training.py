"""Strong contracts for target definitions, temporal folds and qualification."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .core import FrozenModel
from .v2_base import CapabilityStatus


class TargetDefinition(FrozenModel):
    target_id: str = Field(min_length=1)
    target_family: str = Field(min_length=1)
    economic_definition: str = Field(min_length=1)
    transformation: str = Field(min_length=1)
    units: str = Field(min_length=1)
    sign_convention: str = Field(min_length=1)
    event_time_definition: str = Field(min_length=1)
    available_time_definition: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    trading_calendar_id: str = Field(min_length=1)
    minimum_history: int = Field(ge=8)
    capability_requirements: tuple[str, ...] = ()
    availability_status: CapabilityStatus


class TemporalPartition(FrozenModel):
    name: Literal["TRAIN", "VALIDATION", "CALIBRATION", "TEST"]
    timestamps: tuple[datetime, ...] = Field(min_length=1)

    @field_validator("timestamps")
    @classmethod
    def utc_sorted(cls, values: tuple[datetime, ...]) -> tuple[datetime, ...]:
        normalized = tuple(value.astimezone(timezone.utc) for value in values)
        if normalized != tuple(sorted(normalized)) or len(normalized) != len(set(normalized)):
            raise ValueError("partition timestamps must be unique and sorted")
        return normalized


class TemporalFold(FrozenModel):
    fold_id: str = Field(min_length=1)
    window_type: Literal["EXPANDING", "ROLLING", "ANCHORED"]
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    partitions: tuple[TemporalPartition, ...] = Field(min_length=4, max_length=4)
    purge_count: int = Field(ge=0)
    embargo_sessions: int = Field(ge=0)
    calendar_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> "TemporalFold":
        mapping = {item.name: item.timestamps for item in self.partitions}
        if set(mapping) != {"TRAIN", "VALIDATION", "CALIBRATION", "TEST"}:
            raise ValueError("fold must contain four canonical partitions")
        if not max(mapping["TRAIN"]) < min(mapping["VALIDATION"]):
            raise ValueError("TRAIN must precede VALIDATION")
        if not max(mapping["VALIDATION"]) < min(mapping["CALIBRATION"]):
            raise ValueError("VALIDATION must precede CALIBRATION")
        if not max(mapping["CALIBRATION"]) < min(mapping["TEST"]):
            raise ValueError("CALIBRATION must precede sealed TEST")
        return self


class TemporalEvaluationPlan(FrozenModel):
    folds: tuple[TemporalFold, ...] = Field(min_length=2)
    sealed_holdout: Literal["TEST"] = "TEST"
    session_source: str = Field(min_length=1)
    target_specific: bool = True


class ModelBinding(FrozenModel):
    binding_id: str = Field(min_length=1)
    resolver_family: str = Field(min_length=1)
    implementation_id: str = Field(min_length=1)
    target_families: tuple[str, ...] = Field(min_length=1)
    compatible_views: tuple[str, ...] = Field(min_length=1)
    required_features: tuple[str, ...] = ()
    optional_features: tuple[str, ...] = ()
    minimum_sample: int = Field(ge=8)
    resource_budget: dict[str, float | int] = Field(min_length=1)
    capability_status: CapabilityStatus
    role: Literal["CORE", "CHALLENGER", "RESERVE", "SHADOW"]
    parameters: dict[str, float | int | str | bool] = Field(default_factory=dict)


class QualificationDecision(FrozenModel):
    resolver_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    classification: Literal[
        "CHAMPION", "QUALIFIED_CHALLENGER", "SHADOW", "REJECTED", "INSUFFICIENT_EVIDENCE"
    ]
    reason_codes: tuple[str, ...] = ()
    baseline_resolver_id: str = Field(min_length=1)
    fold_count: int = Field(ge=0)
    deterministic: bool
