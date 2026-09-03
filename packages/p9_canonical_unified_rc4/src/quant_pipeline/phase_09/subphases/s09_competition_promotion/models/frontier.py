from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints, field_validator, model_validator

from ..enums import (
    ContaminationState,
    FrontierState,
    GateState,
    ParameterRegionState,
)
from .common import ConfigId, MetricValue, NonEmptyStr, StrictModel

ParameterScalar = bool | int | float | str
ParameterName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


class ParameterValue(StrictModel):
    name: ParameterName
    value: ParameterScalar


class ParameterDimension(StrictModel):
    name: ParameterName
    numeric_minimum: float | None = None
    numeric_maximum: float | None = None
    allowed_categories: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_dimension(self) -> "ParameterDimension":
        numeric = self.numeric_minimum is not None or self.numeric_maximum is not None
        categorical = bool(self.allowed_categories)
        if numeric == categorical:
            raise ValueError("parameter dimensions must be numeric xor categorical")
        if numeric:
            if self.numeric_minimum is None or self.numeric_maximum is None:
                raise ValueError("numeric dimensions require both bounds")
            if self.numeric_minimum >= self.numeric_maximum:
                raise ValueError("numeric parameter minimum must be below maximum")
        if len(set(self.allowed_categories)) != len(self.allowed_categories):
            raise ValueError("allowed categories must be unique")
        return self


class ParameterSpaceRegistry(StrictModel):
    schema_version: NonEmptyStr
    dimensions: tuple[ParameterDimension, ...]

    @model_validator(mode="after")
    def validate_unique_dimensions(self) -> "ParameterSpaceRegistry":
        names = [dimension.name for dimension in self.dimensions]
        if len(set(names)) != len(names):
            raise ValueError("parameter dimension names must be unique")
        return self


class GateObservation(StrictModel):
    gate_id: NonEmptyStr
    state: GateState


class ConfigurationEvaluationCard(StrictModel):
    configuration_id: ConfigId
    cohort_id: NonEmptyStr
    parameters: tuple[ParameterValue, ...]
    metrics: tuple[MetricValue, ...]
    gates: tuple[GateObservation, ...]
    model_confidence_set_member: bool
    complexity_score: float = Field(ge=0.0)
    pbo: float = Field(ge=0.0, le=1.0)
    dsr: float = Field(ge=0.0, le=1.0)
    contamination_state: ContaminationState = ContaminationState.UNKNOWN
    critical_regime_failures: tuple[NonEmptyStr, ...] = ()
    live_evidence_available: bool = False
    live_degradation_detected: bool = False
    capacity_feasible: bool = True
    stress_resilient: bool = True

    @model_validator(mode="after")
    def validate_unique_fields(self) -> "ConfigurationEvaluationCard":
        parameter_names = [item.name for item in self.parameters]
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("configuration parameters must be unique")
        metric_ids = [item.metric_id for item in self.metrics]
        if len(set(metric_ids)) != len(metric_ids):
            raise ValueError("configuration metric IDs must be unique")
        gate_ids = [item.gate_id for item in self.gates]
        if len(set(gate_ids)) != len(gate_ids):
            raise ValueError("configuration gate IDs must be unique")
        return self

    def metric_map(self) -> dict[str, float]:
        return {item.metric_id: item.value for item in self.metrics}

    def gate_map(self) -> dict[str, GateState]:
        return {item.gate_id: item.state for item in self.gates}

    def parameter_map(self) -> dict[str, ParameterScalar]:
        return {item.name: item.value for item in self.parameters}


class DominatedConfiguration(StrictModel):
    configuration_id: ConfigId
    dominated_by: tuple[ConfigId, ...]
    reason: NonEmptyStr


class ParameterRegion(StrictModel):
    region_id: NonEmptyStr
    cohort_id: NonEmptyStr
    member_configuration_ids: tuple[ConfigId, ...]
    state: ParameterRegionState
    mean_utility: float
    minimum_primary_lower_bound: float
    utility_dispersion: float = Field(ge=0.0)
    boundary_fraction: float = Field(ge=0.0, le=1.0)


class CohortFrontier(StrictModel):
    cohort_id: NonEmptyStr
    frontier_configuration_ids: tuple[ConfigId, ...]
    eligible_configuration_ids: tuple[ConfigId, ...]
    ineligible_configuration_ids: tuple[ConfigId, ...]
    robust_regions: tuple[ParameterRegion, ...]
    dominated: tuple[DominatedConfiguration, ...]


class RobustConfigurationFrontier(StrictModel):
    state: FrontierState
    cohorts: tuple[CohortFrontier, ...]
    warnings: tuple[NonEmptyStr, ...] = ()

    @field_validator("cohorts")
    @classmethod
    def unique_cohorts(cls, value: tuple[CohortFrontier, ...]) -> tuple[CohortFrontier, ...]:
        ids = [item.cohort_id for item in value]
        if len(set(ids)) != len(ids):
            raise ValueError("cohort IDs must be unique")
        return value


class FrontierBuildPolicy(StrictModel):
    neighbor_radius: float = Field(gt=0.0, le=1.0, default=0.2)
    minimum_region_size: int = Field(ge=1, default=3)
    maximum_utility_dispersion: float = Field(ge=0.0, default=0.1)
    boundary_tolerance: float = Field(ge=0.0, le=0.5, default=0.02)
    primary_lower_bound_metric_id: NonEmptyStr = "competition_score_lower_bound"
