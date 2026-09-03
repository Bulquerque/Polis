from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .economic_models import ExecutionStatus, HorizonGroup, MissingnessState, QualityState, _require_aware


class AlignmentDirection(StrEnum):
    BACKWARD = "BACKWARD"


class AnchorMode(StrEnum):
    UNION_OBSERVED_TIMES = "UNION_OBSERVED_TIMES"


class ConflictMode(StrEnum):
    SIGNED_DIRECTIONAL = "SIGNED_DIRECTIONAL"
    MAGNITUDE_DISPERSION = "MAGNITUDE_DISPERSION"


class InteractionOperation(StrEnum):
    SIGN_AGREEMENT = "SIGN_AGREEMENT"
    SAFE_RATIO = "SAFE_RATIO"
    NONNEGATIVE_GEOMETRIC_MEAN = "NONNEGATIVE_GEOMETRIC_MEAN"


class FeatureKind(StrEnum):
    PERSPECTIVE = "PERSPECTIVE"
    CONFLICT = "CONFLICT"
    INTERACTION = "INTERACTION"


class AlignmentPolicyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    horizon_group: HorizonGroup
    max_age_seconds: int = Field(ge=0)
    emit_missing_records: bool = True


class BroadcastRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature_id: str = Field(min_length=1)
    source_entity_id: str = Field(min_length=1)
    target_scope: str = Field(pattern=r"^ALL_LOCAL_ENTITIES$")
    excluded_target_entity_ids: tuple[str, ...] = ()


class AlignmentPolicyRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    lineage_id: str = Field(min_length=1)
    direction: AlignmentDirection = AlignmentDirection.BACKWARD
    anchor_mode: AnchorMode = AnchorMode.UNION_OBSERVED_TIMES
    max_output_records: int = Field(gt=0, le=10_000_000)
    global_entity_ids: tuple[str, ...] = ()
    policies: tuple[AlignmentPolicyRecord, ...]
    broadcast_rules: tuple[BroadcastRule, ...] = ()

    @model_validator(mode="after")
    def validate_registry(self) -> "AlignmentPolicyRegistry":
        _require_aware(self.as_of_time, "as_of_time")
        horizons = [row.horizon_group for row in self.policies]
        if len(horizons) != len(set(horizons)):
            raise ValueError("duplicate horizon alignment policies")
        feature_ids = [row.feature_id for row in self.broadcast_rules]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("duplicate broadcast rules")
        return self


class ConflictMemberSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature_id: str = Field(min_length=1)
    direction_multiplier: int = Field(ge=-1, le=1)
    independence_group: str = Field(min_length=1)
    weight: float = Field(gt=0)

    @field_validator("direction_multiplier")
    @classmethod
    def nonzero_direction(cls, value: int) -> int:
        if value == 0:
            raise ValueError("direction_multiplier must be -1 or 1")
        return value


class ConflictGroupSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    group_id: str = Field(min_length=1)
    output_prefix: str = Field(min_length=1)
    phenomenon_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    mode: ConflictMode
    min_views: int = Field(ge=2)
    members: tuple[ConflictMemberSpec, ...]
    enabled: bool = True

    @model_validator(mode="after")
    def validate_members(self) -> "ConflictGroupSpec":
        feature_ids = [row.feature_id for row in self.members]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("conflict group contains duplicate members")
        if self.min_views > len(self.members):
            raise ValueError("min_views cannot exceed member count")
        return self


class ConflictGroupRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    lineage_id: str = Field(min_length=1)
    records: tuple[ConflictGroupSpec, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> "ConflictGroupRegistry":
        _require_aware(self.as_of_time, "as_of_time")
        ids = [row.group_id for row in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate conflict groups")
        return self


class InteractionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    interaction_id: str = Field(min_length=1)
    output_feature_id: str = Field(min_length=1)
    phenomenon_id: str = Field(min_length=1)
    perspective_id: str = Field(min_length=1)
    horizon_group: HorizonGroup
    operation: InteractionOperation
    parent_feature_ids: tuple[str, ...]
    rationale_id: str = Field(min_length=1)
    strong_heredity: bool = True
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_spec(self) -> "InteractionSpec":
        if not 2 <= len(self.parent_feature_ids) <= 3:
            raise ValueError("interactions require two or three parents")
        if len(self.parent_feature_ids) != len(set(self.parent_feature_ids)):
            raise ValueError("interaction parents must be unique")
        if not self.strong_heredity:
            raise ValueError("S6 interactions require strong heredity")
        if self.operation is InteractionOperation.SAFE_RATIO:
            epsilon = self.parameters.get("epsilon")
            if not isinstance(epsilon, (int, float)) or epsilon <= 0:
                raise ValueError("SAFE_RATIO requires a positive explicit epsilon")
        return self


class ApprovedInteractionRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    pipeline_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    cycle_id: str = Field(min_length=1)
    as_of_time: datetime
    lineage_id: str = Field(min_length=1)
    maximum_interactions: int = Field(gt=0, le=500)
    records: tuple[InteractionSpec, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> "ApprovedInteractionRegistry":
        _require_aware(self.as_of_time, "as_of_time")
        enabled = [row for row in self.records if row.enabled]
        if len(enabled) > self.maximum_interactions:
            raise ValueError("enabled interactions exceed approved budget")
        ids = [(row.interaction_id, row.output_feature_id) for row in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate interaction IDs or outputs")
        return self


