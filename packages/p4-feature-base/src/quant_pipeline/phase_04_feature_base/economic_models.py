from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class QualityState(StrEnum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class MissingnessState(StrEnum):
    OBSERVED = "OBSERVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_YET_PUBLISHED = "NOT_YET_PUBLISHED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    LATE_ARRIVAL = "LATE_ARRIVAL"
    STALE = "STALE"
    STRUCTURALLY_MISSING = "STRUCTURALLY_MISSING"
    QUALITY_BLOCKED = "QUALITY_BLOCKED"
    UNAVAILABLE_UPSTREAM = "UNAVAILABLE_UPSTREAM"


class ExecutionStatus(StrEnum):
    PRODUCED = "PRODUCED"
    DEGRADED = "DEGRADED"
    SKIPPED_NOT_AUTHORIZED = "SKIPPED_NOT_AUTHORIZED"
    UNAVAILABLE_UPSTREAM = "UNAVAILABLE_UPSTREAM"
    FAILED_NONBLOCKING = "FAILED_NONBLOCKING"
    BLOCKED = "BLOCKED"


class HorizonGroup(StrEnum):
    INTRADAY = "INTRADAY"
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"
    CROSS_HORIZON = "CROSS_HORIZON"


class ExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    pipeline_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_times(self) -> "ExecutionContext":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot be before as_of_time")
        return self


class CanonicalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_time: datetime
    entity_id: str = Field(min_length=1)
    variable_id: str = Field(min_length=1)
    value: float | int | str | bool | None
    source_modality: str = Field(min_length=1)
    available_at: datetime
    quality_state: QualityState
    missingness_state: MissingnessState
    record_lineage_id: str = Field(min_length=1)
    reference_time: datetime | None = None
    event_time: datetime | None = None
    published_at: datetime | None = None
    source_id: str | None = None
    unit: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value")
    @classmethod
    def finite_numeric_value(cls, value: float | int | str | bool | None) -> float | int | str | bool | None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric values must be finite")
        return value

    @model_validator(mode="after")
    def point_in_time(self) -> "CanonicalObservation":
        for name in ("decision_time", "available_at", "reference_time", "event_time", "published_at"):
            value = getattr(self, name)
            if value is not None:
                _require_aware(value, name)
        if self.available_at > self.decision_time:
            raise ValueError("available_at cannot be after decision_time")
        if self.quality_state is QualityState.BLOCKED and self.missingness_state is MissingnessState.OBSERVED:
            raise ValueError("blocked observations cannot be marked OBSERVED")
        return self


class CanonicalObservationPanel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    lineage_id: str = Field(min_length=1)
    records: tuple[CanonicalObservation, ...]

    @model_validator(mode="after")
    def validate_panel(self) -> "CanonicalObservationPanel":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot be before as_of_time")
        if any(row.decision_time > self.as_of_time or row.available_at > self.as_of_time for row in self.records):
            raise ValueError("panel contains observations after as_of_time")
        return self


class ObserverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observer_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    parameterization_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class ObserverExecutionRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    lineage_id: str = Field(min_length=1)
    records: tuple[ObserverSpec, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> "ObserverExecutionRegistry":
        _require_aware(self.as_of_time, "as_of_time")
        keys = [(row.module_id, row.observer_id, row.parameterization_id) for row in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("registry contains duplicate observer parameterizations")
        return self


class AtomicFeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_time: datetime
    entity_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    observer_id: str = Field(min_length=1)
    parameterization_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    value: float | None
    unit: str = Field(min_length=1)
    available_at: datetime
    source_modalities: tuple[str, ...]
    quality_state: QualityState
    missingness_state: MissingnessState
    record_lineage_id: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("feature values must be finite")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> "AtomicFeatureRecord":
        _require_aware(self.decision_time, "decision_time")
        _require_aware(self.available_at, "available_at")
        if self.available_at > self.decision_time:
            raise ValueError("feature available_at cannot be after decision_time")
        if self.value is None and self.missingness_state is MissingnessState.OBSERVED:
            raise ValueError("missing feature value cannot be OBSERVED")
        return self


class AtomicFeaturePanel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    artifact_name: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    phase_id: str = "P4"
    subphase_id: str = "P4.S4"
    producer_module_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)
    execution_status: ExecutionStatus
    quality_status: QualityState
    quality_reasons: tuple[str, ...] = ()
    records: tuple[AtomicFeatureRecord, ...]

    @model_validator(mode="after")
    def validate_panel(self) -> "AtomicFeaturePanel":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot be before as_of_time")
        if any(row.decision_time > self.as_of_time or row.available_at > self.as_of_time for row in self.records):
            raise ValueError("feature panel contains records after as_of_time")
        keys = [
            (row.decision_time, row.entity_id, row.feature_id, row.parameterization_id)
            for row in self.records
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("feature panel contains duplicate feature records")
        return self
