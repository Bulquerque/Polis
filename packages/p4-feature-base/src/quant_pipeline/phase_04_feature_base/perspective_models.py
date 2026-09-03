from __future__ import annotations

from datetime import datetime
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .economic_models import ExecutionStatus, HorizonGroup, MissingnessState, QualityState, _require_aware


class PerspectiveSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis_id: str = Field(min_length=1)
    observer_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    phenomenon_id: str = Field(min_length=1)
    perspective_id: str = Field(min_length=1)
    parameterization_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    source_feature_ids: tuple[str, ...]
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class PerspectiveExecutionRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    lineage_id: str = Field(min_length=1)
    records: tuple[PerspectiveSpec, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> "PerspectiveExecutionRegistry":
        _require_aware(self.as_of_time, "as_of_time")
        keys = [(r.module_id, r.observer_id, r.parameterization_id) for r in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("registry contains duplicate perspective parameterizations")
        hypotheses = [r.hypothesis_id for r in self.records if r.enabled]
        if len(hypotheses) != len(set(hypotheses)):
            raise ValueError("enabled foundational hypotheses must be unique")
        if len(hypotheses) != 32:
            raise ValueError("exactly 32 foundational hypotheses must be enabled")
        return self


class PerspectiveFeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_time: datetime
    entity_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    phenomenon_id: str = Field(min_length=1)
    perspective_id: str = Field(min_length=1)
    observer_id: str = Field(min_length=1)
    parameterization_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    value: float | None
    unit: str = Field(min_length=1)
    sign_convention: str = Field(min_length=1)
    available_at: datetime
    source_modalities: tuple[str, ...]
    source_feature_ids: tuple[str, ...]
    quality_state: QualityState
    missingness_state: MissingnessState
    record_lineage_id: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("perspective values must be finite")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> "PerspectiveFeatureRecord":
        _require_aware(self.decision_time, "decision_time")
        _require_aware(self.available_at, "available_at")
        if self.available_at > self.decision_time:
            raise ValueError("perspective available_at cannot be after decision_time")
        if self.value is None and self.missingness_state is MissingnessState.OBSERVED:
            raise ValueError("missing value cannot be OBSERVED")
        return self


class PerspectiveFeaturePanel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    artifact_name: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    phase_id: str = "P4"
    subphase_id: str = "P4.S5"
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
    records: tuple[PerspectiveFeatureRecord, ...]

    @model_validator(mode="after")
    def validate_panel(self) -> "PerspectiveFeaturePanel":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        if self.created_at < self.as_of_time:
            raise ValueError("created_at cannot be before as_of_time")
        keys = [(r.decision_time, r.entity_id, r.feature_id, r.parameterization_id) for r in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("perspective panel contains duplicate records")
        if any(r.decision_time > self.as_of_time or r.available_at > self.as_of_time for r in self.records):
            raise ValueError("perspective panel contains future records")
        return self
