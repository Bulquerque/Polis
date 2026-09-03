from __future__ import annotations

from pydantic import Field, model_validator

from .base import (
    ConditionOperator,
    NonEmptyStr,
    ParameterId,
    ParameterKind,
    ParameterScale,
    ReasonCode,
    SearchSpaceState,
    Sha256Hex,
    StrictModel,
)
from .experiment import ValidatedExperimentSpecification
from .parameters import HyperparameterSchemaSnapshot, ParameterScalar


class ActivationCondition(StrictModel):
    parent_parameter_id: ParameterId
    operator: ConditionOperator
    values: tuple[ParameterScalar, ...]

    @model_validator(mode="after")
    def validate_values(self) -> "ActivationCondition":
        if not self.values:
            raise ValueError("activation condition requires values")
        return self


class SearchDomain(StrictModel):
    parameter_id: ParameterId
    kind: ParameterKind
    scale: ParameterScale = ParameterScale.LINEAR
    discrete_values: tuple[ParameterScalar, ...] = ()
    lower: int | float | None = None
    upper: int | float | None = None
    grid_points: int | None = Field(default=None, ge=2, le=10000)
    active_when: tuple[ActivationCondition, ...] = ()

    @model_validator(mode="after")
    def validate_domain(self) -> "SearchDomain":
        if self.discrete_values:
            if self.lower is not None or self.upper is not None or self.grid_points is not None:
                raise ValueError("discrete domain cannot also define continuous bounds")
            if len(self.discrete_values) != len(set(self.discrete_values)):
                raise ValueError("discrete values must be unique")
        else:
            if self.kind not in {ParameterKind.INTEGER, ParameterKind.FLOAT}:
                raise ValueError("non-numeric search domain requires discrete values")
            if self.lower is None or self.upper is None:
                raise ValueError("numeric domain requires lower and upper")
            if self.lower >= self.upper:
                raise ValueError("search lower must be < upper")
            if self.scale is ParameterScale.LOG and self.lower <= 0:
                raise ValueError("log search domain requires positive lower bound")
        return self


class SearchSpaceDeclaration(StrictModel):
    declaration_id: NonEmptyStr
    domains: tuple[SearchDomain, ...]
    maximum_exact_cardinality: int = Field(default=100000, ge=1)
    maximum_allowed_upper_bound: int = Field(default=100000000, ge=1)

    @model_validator(mode="after")
    def validate_unique(self) -> "SearchSpaceDeclaration":
        ids = [domain.parameter_id for domain in self.domains]
        if not ids:
            raise ValueError("search space requires at least one domain")
        if len(ids) != len(set(ids)):
            raise ValueError("search domains must have unique parameter IDs")
        return self


class CompiledParameterDomain(StrictModel):
    parameter_id: ParameterId
    kind: ParameterKind
    scale: ParameterScale
    discrete_values: tuple[ParameterScalar, ...] = ()
    lower: int | float | None = None
    upper: int | float | None = None
    grid_points: int | None = None
    active_when: tuple[ActivationCondition, ...] = ()
    topological_index: int = Field(ge=0)

    def is_finite(self) -> bool:
        return bool(self.discrete_values) or self.grid_points is not None


class SearchSpaceConstraintEdge(StrictModel):
    parent_parameter_id: ParameterId
    child_parameter_id: ParameterId


class SearchSpaceConstraintGraph(StrictModel):
    parameter_order: tuple[ParameterId, ...]
    edges: tuple[SearchSpaceConstraintEdge, ...] = ()


class SearchSpaceCardinalityReport(StrictModel):
    finite: bool
    exact_cardinality: int | None = Field(default=None, ge=0)
    upper_bound: int | None = Field(default=None, ge=0)
    effective_dimension_count: int = Field(ge=0)
    conditional_parameter_count: int = Field(ge=0)
    inactive_parameter_ids: tuple[ParameterId, ...] = ()
    boundary_only_parameter_ids: tuple[ParameterId, ...] = ()

    @model_validator(mode="after")
    def validate_cardinality(self) -> "SearchSpaceCardinalityReport":
        if self.finite and self.upper_bound is None:
            raise ValueError("finite space requires upper bound")
        if self.exact_cardinality is not None and self.upper_bound is not None:
            if self.exact_cardinality > self.upper_bound:
                raise ValueError("exact cardinality cannot exceed upper bound")
        return self


class CompiledSearchSpace(StrictModel):
    space_id: NonEmptyStr
    experiment_id: NonEmptyStr
    specification_sha256: Sha256Hex
    state: SearchSpaceState
    parameters: tuple[CompiledParameterDomain, ...]
    constraint_graph: SearchSpaceConstraintGraph
    cardinality: SearchSpaceCardinalityReport
    space_sha256: Sha256Hex
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_compiled(self) -> "CompiledSearchSpace":
        ids = [parameter.parameter_id for parameter in self.parameters]
        if len(ids) != len(set(ids)):
            raise ValueError("compiled parameters must be unique")
        if tuple(ids) != self.constraint_graph.parameter_order:
            raise ValueError("compiled parameter order must match constraint graph")
        blocking = {
            SearchSpaceState.SPACE_EMPTY,
            SearchSpaceState.SPACE_EXPLOSIVE,
            SearchSpaceState.SPACE_INVALID,
        }
        if self.state in blocking and not self.reason_codes:
            raise ValueError("blocking search space state requires reason codes")
        return self


class SearchSpaceCompilationInput(StrictModel):
    validated_specification: ValidatedExperimentSpecification
    parameter_snapshot: HyperparameterSchemaSnapshot
    declaration: SearchSpaceDeclaration


class SearchSpaceCompilationOutcome(StrictModel):
    compiled_space: CompiledSearchSpace | None
