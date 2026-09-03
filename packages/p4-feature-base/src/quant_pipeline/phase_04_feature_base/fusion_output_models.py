from __future__ import annotations

from datetime import datetime
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .economic_models import ExecutionStatus, HorizonGroup, MissingnessState, QualityState, _require_aware
from .fusion_registry_models import ConflictMode, FeatureKind, InteractionOperation

class AlignedPerspectiveRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_time: datetime
    source_decision_time: datetime | None
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
    information_age_seconds: float | None
    source_modalities: tuple[str, ...]
    source_feature_ids: tuple[str, ...]
    quality_state: QualityState
    missingness_state: MissingnessState
    record_lineage_id: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value", "information_age_seconds")
    @classmethod
    def finite_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("aligned numeric values must be finite")
        return value

    @model_validator(mode="after")
    def validate_record(self) -> "AlignedPerspectiveRecord":
        _require_aware(self.decision_time, "decision_time")
        _require_aware(self.available_at, "available_at")
        if self.source_decision_time is not None:
            _require_aware(self.source_decision_time, "source_decision_time")
            if self.source_decision_time > self.decision_time:
                raise ValueError("alignment cannot use a future source record")
        if self.available_at > self.decision_time:
            raise ValueError("aligned available_at cannot exceed decision_time")
        if self.information_age_seconds is not None and self.information_age_seconds < 0:
            raise ValueError("information age cannot be negative")
        if self.value is None and self.missingness_state is MissingnessState.OBSERVED:
            raise ValueError("missing aligned value cannot be OBSERVED")
        return self


class AlignedPerspectivePanel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    artifact_name: str = "aligned_perspective_panel"
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    phase_id: str = "P4"
    subphase_id: str = "P4.S6"
    producer_module_id: str = "P4.S6.M01"
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)
    execution_status: ExecutionStatus
    quality_status: QualityState
    quality_reasons: tuple[str, ...] = ()
    records: tuple[AlignedPerspectiveRecord, ...]

    @model_validator(mode="after")
    def validate_panel(self) -> "AlignedPerspectivePanel":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        keys = [(r.decision_time, r.entity_id, r.feature_id, r.parameterization_id) for r in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("aligned panel contains duplicate records")
        if any(r.decision_time > self.as_of_time for r in self.records):
            raise ValueError("aligned panel contains future records")
        return self


class ConflictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_time: datetime
    entity_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    output_prefix: str = Field(min_length=1)
    phenomenon_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    mode: ConflictMode
    consensus_score: float | None
    conflict_score: float | None
    dispersion_score: float | None
    entropy_score: float | None
    minority_view_strength: float | None
    available_view_count: int = Field(ge=0)
    independent_view_count: int = Field(ge=0)
    expected_view_count: int = Field(gt=0)
    dominant_modality: str | None
    available_at: datetime
    source_modalities: tuple[str, ...] = ()
    quality_state: QualityState
    missingness_state: MissingnessState
    record_lineage_id: str = Field(min_length=1)
    source_feature_ids: tuple[str, ...]
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_record(self) -> "ConflictRecord":
        _require_aware(self.decision_time, "decision_time")
        _require_aware(self.available_at, "available_at")
        if self.available_at > self.decision_time:
            raise ValueError("conflict available_at cannot exceed decision_time")
        if self.available_view_count > self.expected_view_count:
            raise ValueError("available views cannot exceed expected views")
        return self


class PerspectiveConflictPanel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    artifact_name: str = "perspective_conflict_panel"
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    phase_id: str = "P4"
    subphase_id: str = "P4.S6"
    producer_module_id: str = "P4.S6.M02"
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)
    execution_status: ExecutionStatus
    quality_status: QualityState
    quality_reasons: tuple[str, ...] = ()
    records: tuple[ConflictRecord, ...]

    @model_validator(mode="after")
    def validate_panel(self) -> "PerspectiveConflictPanel":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        keys=[(r.decision_time,r.entity_id,r.group_id) for r in self.records]
        if len(keys)!=len(set(keys)): raise ValueError("conflict panel contains duplicate records")
        if any(r.decision_time>self.as_of_time for r in self.records): raise ValueError("conflict panel contains future records")
        return self


class InteractionFeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_time: datetime
    entity_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    interaction_id: str = Field(min_length=1)
    phenomenon_id: str = Field(min_length=1)
    perspective_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    operation: InteractionOperation
    value: float | None
    unit: str = Field(min_length=1)
    parent_feature_ids: tuple[str, ...]
    available_at: datetime
    source_modalities: tuple[str, ...] = ()
    quality_state: QualityState
    missingness_state: MissingnessState
    record_lineage_id: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("interaction values must be finite")
        return value

    @model_validator(mode="after")
    def validate_time(self) -> "InteractionFeatureRecord":
        _require_aware(self.decision_time, "decision_time")
        _require_aware(self.available_at, "available_at")
        if self.available_at > self.decision_time:
            raise ValueError("interaction available_at cannot exceed decision_time")
        return self


class InteractionFeaturePanel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    artifact_name: str = "interaction_feature_panel"
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    phase_id: str = "P4"
    subphase_id: str = "P4.S6"
    producer_module_id: str = "P4.S6.M03"
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)
    execution_status: ExecutionStatus
    quality_status: QualityState
    quality_reasons: tuple[str, ...] = ()
    records: tuple[InteractionFeatureRecord, ...]

    @model_validator(mode="after")
    def validate_panel(self) -> "InteractionFeaturePanel":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        keys=[(r.decision_time,r.entity_id,r.feature_id) for r in self.records]
        if len(keys)!=len(set(keys)): raise ValueError("interaction panel contains duplicate records")
        if any(r.decision_time>self.as_of_time for r in self.records): raise ValueError("interaction panel contains future records")
        return self


class HorizonFeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_time: datetime
    entity_id: str = Field(min_length=1)
    feature_id: str = Field(min_length=1)
    feature_kind: FeatureKind
    phenomenon_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    value: float | None
    unit: str = Field(min_length=1)
    available_at: datetime
    information_age_seconds: float | None
    is_observed: bool
    quality_state: QualityState
    missingness_state: MissingnessState
    source_feature_ids: tuple[str, ...]
    source_modalities: tuple[str, ...] = ()
    record_lineage_id: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_time(self) -> "HorizonFeatureRecord":
        _require_aware(self.decision_time, "decision_time")
        _require_aware(self.available_at, "available_at")
        if self.available_at > self.decision_time:
            raise ValueError("horizon feature available_at cannot exceed decision_time")
        if self.information_age_seconds is not None and self.information_age_seconds < 0:
            raise ValueError("information_age_seconds cannot be negative")
        return self


class HorizonFeaturePanel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    artifact_name: str = "horizon_feature_panel"
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    phase_id: str = "P4"
    subphase_id: str = "P4.S6"
    producer_module_id: str = "P4.S6.M04"
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)
    execution_status: ExecutionStatus
    quality_status: QualityState
    quality_reasons: tuple[str, ...] = ()
    records: tuple[HorizonFeatureRecord, ...]

    @model_validator(mode="after")
    def validate_panel(self) -> "HorizonFeaturePanel":
        _require_aware(self.as_of_time, "as_of_time")
        _require_aware(self.created_at, "created_at")
        keys=[(r.decision_time,r.entity_id,r.feature_id,r.feature_kind) for r in self.records]
        if len(keys)!=len(set(keys)): raise ValueError("horizon panel contains duplicate records")
        if any(r.decision_time>self.as_of_time for r in self.records): raise ValueError("horizon panel contains future records")
        return self


class HorizonFeatureManifestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature_id: str = Field(min_length=1)
    feature_kind: FeatureKind
    phenomenon_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    source_feature_ids: tuple[str, ...]
    total_record_count: int = Field(ge=0)
    observed_record_count: int = Field(ge=0)
    coverage_rate: float = Field(ge=0, le=1)
    first_decision_time: datetime | None
    last_decision_time: datetime | None
    maximum_information_age_seconds: float | None
    quality_state: QualityState


class HorizonFeatureSetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    artifact_name: str = "horizon_feature_set_manifest"
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    phase_id: str = "P4"
    subphase_id: str = "P4.S6"
    producer_module_id: str = "P4.S6.M04"
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    created_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)
    records: tuple[HorizonFeatureManifestRecord, ...]
