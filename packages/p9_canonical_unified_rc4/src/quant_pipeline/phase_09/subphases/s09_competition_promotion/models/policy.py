from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from ..enums import OptimizationDirection, PolicyCompileState
from .common import NonEmptyStr, PolicyId, StrictModel, UtcTimestampedModel


class HardGateRule(StrictModel):
    gate_id: NonEmptyStr
    accepted_states: tuple[NonEmptyStr, ...] = ("PASS", "PASS_WITH_LIMITATIONS")
    missing_is_failure: bool = True

    @field_validator("accepted_states")
    @classmethod
    def accepted_states_not_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("accepted_states cannot be empty")
        if len(set(value)) != len(value):
            raise ValueError("accepted_states must be unique")
        return value


class SoftPenaltyRule(StrictModel):
    metric_id: NonEmptyStr
    direction: OptimizationDirection
    weight: float = Field(gt=0.0, le=100.0)
    reference_value: float
    scale: float = Field(gt=0.0)
    cap: float = Field(ge=0.0, default=10.0)


class TieBreakerRule(StrictModel):
    metric_id: NonEmptyStr
    direction: OptimizationDirection
    priority: int = Field(ge=1)


class FrontierAxis(StrictModel):
    metric_id: NonEmptyStr
    direction: OptimizationDirection
    epsilon: float = Field(ge=0.0, default=0.0)


class CompetitionObjectiveSpec(UtcTimestampedModel):
    policy_id: PolicyId
    policy_version: NonEmptyStr
    primary_score_id: NonEmptyStr
    primary_score_version: NonEmptyStr
    primary_direction: OptimizationDirection
    hard_gates: tuple[HardGateRule, ...]
    soft_penalties: tuple[SoftPenaltyRule, ...] = ()
    tie_breakers: tuple[TieBreakerRule, ...] = ()
    frontier_axes: tuple[FrontierAxis, ...]
    minimum_effect_size: float = Field(ge=0.0)
    minimum_probability_of_superiority: float = Field(ge=0.5, le=1.0)
    maximum_pbo: float = Field(ge=0.0, le=1.0)
    minimum_dsr: float = Field(ge=0.0, le=1.0)
    maximum_complexity_increase_without_material_gain: float = Field(ge=0.0)
    allowed_deployment_stages: tuple[NonEmptyStr, ...]
    committed_at: datetime
    evaluation_started_at: datetime
    supported_metric_versions: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_spec(self) -> "CompetitionObjectiveSpec":
        if self.committed_at >= self.evaluation_started_at:
            raise ValueError("objective policy must be committed before evaluation starts")
        if self.primary_score_version not in self.supported_metric_versions:
            raise ValueError("primary score version is not supported")
        if not self.hard_gates:
            raise ValueError("at least one hard gate is required")
        if not self.frontier_axes:
            raise ValueError("at least one frontier axis is required")
        gate_ids = [rule.gate_id for rule in self.hard_gates]
        if len(set(gate_ids)) != len(gate_ids):
            raise ValueError("hard gate IDs must be unique")
        penalty_ids = [rule.metric_id for rule in self.soft_penalties]
        if len(set(penalty_ids)) != len(penalty_ids):
            raise ValueError("soft penalty metric IDs must be unique")
        priorities = [rule.priority for rule in self.tie_breakers]
        if len(set(priorities)) != len(priorities):
            raise ValueError("tie-break priorities must be unique")
        axis_ids = [axis.metric_id for axis in self.frontier_axes]
        if len(set(axis_ids)) != len(axis_ids):
            raise ValueError("frontier axis metric IDs must be unique")
        if not self.allowed_deployment_stages:
            raise ValueError("at least one deployment stage must be allowed")
        return self


class CompetitionObjectivePolicy(StrictModel):
    policy_id: PolicyId
    policy_version: NonEmptyStr
    compile_state: PolicyCompileState
    primary_score_id: NonEmptyStr
    primary_score_version: NonEmptyStr
    primary_direction: OptimizationDirection
    hard_gates: tuple[HardGateRule, ...]
    soft_penalties: tuple[SoftPenaltyRule, ...]
    tie_breakers: tuple[TieBreakerRule, ...]
    frontier_axes: tuple[FrontierAxis, ...]
    minimum_effect_size: float
    minimum_probability_of_superiority: float
    maximum_pbo: float
    minimum_dsr: float
    maximum_complexity_increase_without_material_gain: float
    allowed_deployment_stages: tuple[NonEmptyStr, ...]
    committed_at: datetime
    evaluation_started_at: datetime

    @field_validator("committed_at", "evaluation_started_at")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("policy timestamps must be UTC")
        return value
