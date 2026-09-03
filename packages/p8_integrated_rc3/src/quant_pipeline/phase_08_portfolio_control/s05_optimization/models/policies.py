from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .base import Identifier, Sha256, TimeAwareModel
from .enums import RobustMethod


class ObjectivePolicy(TimeAwareModel):
    return_weight: float = Field(ge=0)
    cvar_weight: float = Field(ge=0)
    transaction_cost_weight: float = Field(ge=0)
    turnover_weight: float = Field(ge=0)
    funding_weight: float = Field(ge=0)
    ordinal_penalty_weight: float = Field(ge=0)


class SolverPolicy(TimeAwareModel):
    method: Literal["highs"] = "highs"
    time_limit_seconds: float = Field(gt=0, le=300)
    primal_feasibility_tolerance: float = Field(gt=0, le=1e-4)
    dual_feasibility_tolerance: float = Field(gt=0, le=1e-4)
    objective_tolerance: float = Field(gt=0, le=1e-4)
    presolve: bool = True


class RobustPolicy(TimeAwareModel):
    method: RobustMethod
    enabled: bool
    maximum_probability_shift_l1: float = Field(ge=0, le=2)
    material_quantity_difference: float = Field(ge=0)

    @model_validator(mode="after")
    def method_matches_enabled(self) -> "RobustPolicy":
        if self.enabled == (self.method == RobustMethod.DISABLED):
            raise ValueError("robust method/enabled mismatch")
        return self


class RoundingPolicy(TimeAwareModel):
    use_milp_reoptimization: bool = True
    maximum_objective_degradation: float = Field(ge=0)
    integer_tolerance: float = Field(gt=0, le=1e-4)
    milp_relative_gap: float = Field(ge=0, le=0.1)
    time_limit_seconds: float = Field(gt=0, le=300)


class NoTradePolicy(TimeAwareModel):
    minimum_objective_improvement: float = Field(ge=0)
    minimum_total_quantity_change: float = Field(ge=0)
    hysteresis_multiplier: float = Field(ge=1)
    risk_reduction_override: bool = True


class MPCPolicy(TimeAwareModel):
    planning_horizon_steps: int = Field(ge=1, le=64)
    target_validity_seconds: int = Field(ge=1, le=86400)
    reoptimization_triggers: tuple[Identifier, ...]


class ApprovedPolicyContext(TimeAwareModel):
    policy_id: Identifier
    policy_version: Identifier
    authorized_by: Identifier
    effective_from_cycle: int = Field(ge=0)
    expires_after_cycle: int | None = Field(default=None, ge=0)
    content_sha256: Sha256
    created_at: datetime
    objective: ObjectivePolicy
    solver: SolverPolicy
    robust: RobustPolicy
    rounding: RoundingPolicy
    no_trade: NoTradePolicy
    mpc: MPCPolicy

    @model_validator(mode="after")
    def valid_cycle_window(self) -> "ApprovedPolicyContext":
        if self.expires_after_cycle is not None and self.expires_after_cycle < self.effective_from_cycle:
            raise ValueError("policy expiry precedes effective cycle")
        return self
